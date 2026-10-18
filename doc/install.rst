Build and install
=================

Source code
-----------

Source code for Beremiz is available in
`GitHub <https://github.com/Netzahualcoyotl/beremiz>`_.

Developer setup
---------------

System prerequisites (Ubuntu 26.04)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Install required system packages as root:

.. code-block:: bash

    sudo apt-get install \
      build-essential automake flex bison \
      libpython3.14-dev libssl-dev \
      python3.14 python3-wxgtk4.0 python3-venv \
      inkscape git

Prepare build directory
~~~~~~~~~~~~~~~~~~~~~~~

All commands hereafter assume that selected directory to contain all downloaded
source code and build results is ``~/Beremiz``.

.. code-block:: bash

    mkdir ~/Beremiz
    cd ~/Beremiz

Get source code (Git)
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

    cd ~/Beremiz
    git clone https://github.com/Netzahualcoyotl/beremiz
    git clone https://github.com/Netzahualcoyotl/matiec

Python prerequisites (virtualenv)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

    # Set up the Python virtual environment
    cd ~/Beremiz/beremiz
    # Use the system wxPython package instead of rebuilding it in the venv
    python3 -m venv --system-site-packages .venv
    # Activate the virtual environment
    source .venv/bin/activate
    # Install required Python packages
    python -m pip install -r requirements.txt

Build MatIEC compiler
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

    cd ~/Beremiz/matiec
    autoreconf -i
    ./configure
    make

Build Modbus library (optional)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Only needed for Modbus support.

.. code-block:: bash

    cd ~/Beremiz

    git clone https://github.com/Netzahualcoyotl/Modbus

    cd ~/Beremiz/Modbus
    make

Build CanFestival (optional)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Only needed for CANopen support. Please read the CanFestival manual to choose a
CAN driver other than ``virtual``.

The static libraries are linked into the PLC's shared object, so the build must
be position-independent (``-DCMAKE_POSITION_INDEPENDENT_CODE=ON``).

.. code-block:: bash

    cd ~/Beremiz

    git clone https://github.com/Netzahualcoyotl/CanFestival canfestival

    cd ~/Beremiz/canfestival
    mkdir build && cd build
    cmake .. -DCF_TARGET=unix \
             -DCF_CAN_DRIVER=virtual \
             -DCF_TIMERS_DRIVER=unix \
             -DCMAKE_POSITION_INDEPENDENT_CODE=ON
    make

The Beremiz CANopen extension picks up ``CF_TARGET`` / ``CF_CAN_DRIVER`` /
``CF_TIMERS_DRIVER`` from the resulting ``build/CMakeCache.txt`` and links
against ``build/src/libcanfestival.a`` and ``build/drivers/libcanfestival_<target>.a``,
so rebuilding with a different ``-DCF_CAN_DRIVER`` is enough to switch driver
(no Beremiz changes required).

Build BACnet (optional)
~~~~~~~~~~~~~~~~~~~~~~~

Only needed for BACnet support.

.. code-block:: bash

    cd ~/Beremiz
    git clone https://github.com/Netzahualcoyotl/BACnet
    cd BACnet
    make MAKE_DEFINE='-fPIC' \
         MY_BACNET_DEFINES='-DPRINT_ENABLED=1 -DBACAPP_ALL -DBACFILE \
             -DINTRINSIC_REPORTING -DBACNET_TIME_MASTER \
             -DBACNET_PROPERTY_LISTS=1 -DBACNET_PROTOCOL_REVISION=17' \
         library

Launch Beremiz IDE
~~~~~~~~~~~~~~~~~~

.. code-block:: bash

    cd ~/Beremiz/beremiz
    source .venv/bin/activate
    ./Beremiz.py

Run standalone Beremiz runtime
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Start standalone Beremiz service:

.. code-block:: bash

    mkdir -p ~/Beremiz/beremiz_runtime_workdir
    cd ~/Beremiz/beremiz
    source .venv/bin/activate
    python beremiz/Beremiz_service.py \
        -p 61194 -i localhost -x 0 ~/Beremiz/beremiz_runtime_workdir

To connect IDE with runtime, enter target location URI in project's settings
(``project -> Config -> BeremizRoot/URI_location``) pointed to your running
Beremiz service, in this case::

    ERPC://127.0.0.1:61194

If project's URL is ``LOCAL://``, then IDE launches on demand a local instance
of Beremiz python runtime working on a temporary directory.

Build documentation
-------------------

Source code for documentation is stored in ``doc`` directory in project's
source tree. It's written in reStructuredText (ReST) and uses Sphinx to
generate documentation in different formats.

To build documentation, install the system packages required for
compilation and the Python dependencies in the project's virtual
environment:

.. code-block:: bash

    sudo apt-get install build-essential
    cd ~/Beremiz/beremiz
    source .venv/bin/activate
    python -m pip install sphinx sphinxcontrib-svg2pdfconverter

Documentation in HTML
~~~~~~~~~~~~~~~~~~~~~

The documentation source files are stored in the ``doc`` directory of the
Beremiz source tree. They are written in reStructuredText (ReST) and processed
by Sphinx to generate HTML documentation.

To build the HTML documentation, run:

.. code-block:: bash

    cd ~/Beremiz/beremiz
    source .venv/bin/activate
    cd doc
    make dirhtml

The Makefile uses the ``dirhtml`` builder for the main documentation output.
The generated HTML files are stored in the ``_build/dirhtml`` directory.
Each documentation page is stored as an ``index.html`` file inside its
corresponding directory.

To open the main documentation page in a web browser, run:

.. code-block:: bash

    xdg-open ~/Beremiz/beremiz/doc/_build/dirhtml/index.html

Documentation in PDF
~~~~~~~~~~~~~~~~~~~~

Sphinx can generate a PDF version of the Beremiz documentation using LaTeX.
To build the PDF documentation on Ubuntu/Debian, install the following
system packages:

.. code-block:: bash

    sudo apt-get update
    sudo apt-get install inkscape latexmk texlive-latex-base \
        texlive-latex-recommended texlive-fonts-recommended \
        texlive-latex-extra

Install the Python dependency required to convert SVG images to PDF:

.. code-block:: bash

    cd ~/Beremiz/beremiz
    source .venv/bin/activate
    python -m pip install sphinxcontrib-svg2pdfconverter

Build the PDF documentation:

.. code-block:: bash

    cd ~/Beremiz/beremiz/doc
    make latexpdf

Sphinx generates the LaTeX source files and uses LaTeX to compile them
into a PDF document.

The generated PDF is stored in:

``_build/latex/Beremiz.pdf``

The full path is:

``~/Beremiz/beremiz/doc/_build/latex/Beremiz.pdf``

To open the generated PDF, run:

.. code-block:: bash

    xdg-open ~/Beremiz/beremiz/doc/_build/latex/Beremiz.pdf
