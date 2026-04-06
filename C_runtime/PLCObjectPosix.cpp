#include <string.h>
#include <filesystem>
#include <dlfcn.h>
#include <fstream>
#include <iostream>

#include "Logging.hpp"
#include "PLCObjectPosix.hpp"
#include "BlobPosix.hpp"

// File name of the last transferred PLC md5 hex digest
// with typo in the name, for compatibility with Python runtime
#define LastTransferredPLC "lasttransferedPLC.md5"
#define LastTransferredLogicPLC "lasttransferedPLC_logic.md5"

// File name of the extra files list
#define ExtraFilesList "extra_files.txt"

#if defined(_WIN32) || defined(_WIN64)
// For Windows platform
#define SHARED_OBJECT_EXT ".dll"
#elif defined(__APPLE__) || defined(__MACH__)
// For MacOS platform
#define SHARED_OBJECT_EXT ".dylib"
#else
// For Linux/Unix platform
#define SHARED_OBJECT_EXT ".so"
#endif

#define ULSYM(sym)            \
    do                        \
    {                         \
        m_PLCSyms.sym = NULL; \
    } while (0);

PLCObjectPosix::PLCObjectPosix(void) : PLCObject()
{
    m_handle = NULL;
    m_logic_handle = NULL;
    FOR_EACH_PLC_SYMBOLS_DO(ULSYM);
}

PLCObjectPosix::~PLCObjectPosix(void)
{
}

const char* SharedObjectExtension = SHARED_OBJECT_EXT;

uint32_t PLCObjectPosix::BlobAsFile(
    const binary_t *BlobID, std::filesystem::path filename)
{
    // Extract the blob from the map
    auto nh = m_mapBlobIDToBlob.extract(
        std::vector<uint8_t>(BlobID->data, BlobID->data + BlobID->dataLength));
    if (nh.empty())
    {
        return ENOENT;
    }
    Blob *blob = nh.mapped();

    // Realize the blob into a file
    uint32_t res = dynamic_cast<BlobPosix*>(blob)->asFile(filename);

    DeleteBlob(blob);

    if (res != 0)
    {
        return res;
    }
    return 0;
}

uint32_t PLCObjectPosix::SaveBlobs(
    const char *md5sum,
    const binary_t *plcObjectBlobID,
    const list_extra_file_1_t *extrafiles)
{
    uint32_t res;

    // Create the PLC object shared object file
    res = BlobAsFile(plcObjectBlobID, std::string(md5sum) + SharedObjectExtension);
    if (res != 0)
    {
        return res;
    }

    // create "lasttransferedPLC.md5" file and Save md5sum in it
    std::ofstream(std::string(LastTransferredPLC), std::ios::binary) << md5sum;

    // extrafiles[0] is the logic .so: save it and record its MD5
    if (extrafiles->elementsCount > 0)
    {
        extra_file *logicfile = extrafiles->elements;

        // Logic .so filename is "{logic_md5}.so"; strip extension to get the MD5
        std::string logic_fname(logicfile->fname);
        std::string logic_md5 = logic_fname.substr(0, logic_fname.rfind('.'));

        res = BlobAsFile(&logicfile->blobID, logic_fname);
        if (res != 0)
        {
            return res;
        }

        std::ofstream(std::string(LastTransferredLogicPLC), std::ios::binary) << logic_md5;
    }

    // create "extra_files.txt" for any remaining extra files (indices 1+)
    std::ofstream extra_files_log(std::string(ExtraFilesList), std::ios::binary);

    for (int i = 1; i < extrafiles->elementsCount; i++)
    {
        extra_file *extrafile = extrafiles->elements + i;

        res = BlobAsFile(&extrafile->blobID, extrafile->fname);
        if (res != 0)
        {
            return res;
        }

        // Save the extra file name in "extra_files.txt"
        extra_files_log << extrafile->fname << std::endl;
    }

    return 0;
}

uint32_t PLCObjectPosix::PurgePLC(void)
{
    // Open the extra files list
    std::ifstream extra_files_log(std::string(ExtraFilesList), std::ios::binary);

    // Remove extra files
    std::string extra_file;
    while (std::getline(extra_files_log, extra_file))
    {
        std::filesystem::remove(extra_file);
    }

    // Remove IOs .so
    try {
        std::string md5sum;
        std::ifstream(std::string(LastTransferredPLC), std::ios::binary) >> md5sum;
        std::filesystem::remove(md5sum + SHARED_OBJECT_EXT);
    } catch (std::exception e) {
        // ignored
    }

    // Remove logic .so
    try {
        std::string logic_md5sum;
        std::ifstream(std::string(LastTransferredLogicPLC), std::ios::binary) >> logic_md5sum;
        std::filesystem::remove(logic_md5sum + SHARED_OBJECT_EXT);
    } catch (std::exception e) {
        // ignored
    }

    try {
        std::filesystem::remove(std::string(LastTransferredPLC));
        std::filesystem::remove(std::string(LastTransferredLogicPLC));
        std::filesystem::remove(std::string(ExtraFilesList));
    } catch (std::exception e) {
        // ignored
    }

    return 0;
}

#define DLSYM_IOS(sym)                                                            \
    do                                                                            \
    {                                                                             \
        m_PLCSyms.sym = (decltype(m_PLCSyms.sym))dlsym(m_handle, #sym);           \
        if (m_PLCSyms.sym == NULL)                                                \
        {                                                                         \
            std::cout << "Error dlsym IOs " #sym ": " << dlerror() << std::endl; \
            return errno;                                                         \
        }                                                                         \
    } while (0);

#define DLSYM_LOGIC(sym)                                                            \
    do                                                                              \
    {                                                                               \
        m_PLCSyms.sym = (decltype(m_PLCSyms.sym))dlsym(m_logic_handle, #sym);       \
        if (m_PLCSyms.sym == NULL)                                                  \
        {                                                                           \
            std::cout << "Error dlsym logic " #sym ": " << dlerror() << std::endl; \
            return errno;                                                           \
        }                                                                           \
    } while (0);

uint32_t PLCObjectPosix::LoadPLC(void)
{
    // TODO use PLCLibMutex

    // Load IOs md5
    std::string md5sum;
    try {
        std::ifstream(std::string(LastTransferredPLC), std::ios::binary) >> md5sum;
    } catch (std::exception e) {
        return ENOENT;
    }

    // Load logic md5
    std::string logic_md5sum;
    try {
        std::ifstream(std::string(LastTransferredLogicPLC), std::ios::binary) >> logic_md5sum;
    } catch (std::exception e) {
        return ENOENT;
    }

    // Load IOs .so with RTLD_GLOBAL so its symbols (located vars, logging,
    // global var accessors) are visible when the logic .so resolves externs.
    std::filesystem::path ios_filename(md5sum + SHARED_OBJECT_EXT);
    m_handle = dlopen(std::filesystem::absolute(ios_filename).c_str(), RTLD_NOW | RTLD_GLOBAL);
    if (m_handle == NULL)
    {
        std::cout << "Error loading IOs .so: " << dlerror() << std::endl;
        return errno;
    }

    // Resolve IOs symbols
    FOR_EACH_IOS_SYMBOLS_DO(DLSYM_IOS);

    // Set content of PLC_ID to IOs md5sum
    m_PLCSyms.PLC_ID = (uint8_t *)malloc(md5sum.size() + 1);
    if (m_PLCSyms.PLC_ID == NULL)
    {
        return ENOMEM;
    }
    memcpy(m_PLCSyms.PLC_ID, md5sum.c_str(), md5sum.size());
    m_PLCSyms.PLC_ID[md5sum.size()] = '\0';

    // Load logic .so (externs resolved from IOs RTLD_GLOBAL namespace)
    std::filesystem::path logic_filename(logic_md5sum + SHARED_OBJECT_EXT);
    m_logic_handle = dlopen(std::filesystem::absolute(logic_filename).c_str(), RTLD_NOW);
    if (m_logic_handle == NULL)
    {
        std::cout << "Error loading logic .so: " << dlerror() << std::endl;
        dlclose(m_handle);
        m_handle = NULL;
        return errno;
    }

    // Resolve logic symbols
    FOR_EACH_LOGIC_SYMBOLS_DO(DLSYM_LOGIC);

    // Connect logic to IOs: set plc_logic_run_fn / plc_logic_scan_fn
    // and call config_init__() to initialise the IEC instance tree.
    typedef int (*loadPLCLogic_t)(void *);
    loadPLCLogic_t loadPLCLogic_fn = (loadPLCLogic_t)dlsym(m_handle, "loadPLCLogic");
    if (loadPLCLogic_fn == NULL)
    {
        std::cout << "Error dlsym loadPLCLogic: " << dlerror() << std::endl;
        return errno;
    }
    if (loadPLCLogic_fn(m_logic_handle) != 0)
    {
        std::cout << "Error: loadPLCLogic failed" << std::endl;
        return EINVAL;
    }

    // Call __init_PLCLogic to run config_init__() and initialise the IEC instance tree.
    // Without this, all FB EN flags stay zero (BSS) and FB bodies return immediately.
    typedef int (*init_plc_logic_t)(int, char **);
    init_plc_logic_t init_plc_logic_fn =
        (init_plc_logic_t)dlsym(m_logic_handle, "__init_PLCLogic");
    if (init_plc_logic_fn == NULL)
    {
        std::cout << "Error dlsym __init_PLCLogic: " << dlerror() << std::endl;
        return errno;
    }
    int ilpl_res = init_plc_logic_fn(m_argc, m_argv);
    if (ilpl_res != 0)
    {
        std::cout << "Error: __init_PLCLogic failed: " << ilpl_res << std::endl;
        return EINVAL;
    }

    return 0;
}

uint32_t PLCObjectPosix::UnLoadPLC(void)
{
    FOR_EACH_PLC_SYMBOLS_DO(ULSYM);
    if(m_logic_handle != NULL)
    {
        dlclose(m_logic_handle);
        m_logic_handle = NULL;
    }
    if(m_handle != NULL)
    {
        dlclose(m_handle);
        m_handle = NULL;
    }
    return 0;
}

void PLCObjectPosix::ThreadTrampoline(void){
    // Call the PLCObject::TraceThreadProc method
    PLCObject::TraceThreadProc();
}


void PLCObjectPosix::EnsureDebugThread(void)
{
    // Start debug thread if not already started
    if(!m_traceThread.joinable())
    {
        m_traceThread = std::thread(&PLCObjectPosix::ThreadTrampoline, this);
    }
}

void PLCObjectPosix::StopDebugThread(void)
{
    // Stop debug thread
    if(m_traceThread.joinable())
    {
        m_traceThread.join();
    }
}

void PLCObjectPosix::TraceMutexLock(void)
{
    m_tracesMutex.lock();
}

void PLCObjectPosix::TraceMutexUnlock(void)
{
    m_tracesMutex.unlock();
}

void PLCObjectPosix::PLCLibMutexLock(void)
{
    m_PLClibMutex.lock();
}

void PLCObjectPosix::PLCLibMutexUnlock(void)
{
    m_PLClibMutex.unlock();
}

Blob *PLCObjectPosix::NewBlob()
{
    return new BlobPosix();
}

void PLCObjectPosix::DeleteBlob(Blob *blob)
{
    delete dynamic_cast<BlobPosix*>(blob);
}

std::string PLCObjectPosix::GetLastTransferredPLC_MD5(void)
{
    // Load the last transferred PLC md5 hex digest
    std::string md5sum;
    try {
        std::ifstream(std::string(LastTransferredPLC), std::ios::binary) >> md5sum;
    } catch (std::exception e) {
        return "";
    }

    return md5sum;
}
