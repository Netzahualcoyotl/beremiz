# Free Software Industrial Automation Platform

An independent Free Software project for industrial automation,
based on industrial standards and designed to promote technological
independence, interoperability, and user freedom.

## About This Project

This project aims to develop an integrated industrial automation
platform based on the principles of Free Software.

The objective is to provide an extensible environment for developing,
configuring, programming, monitoring, and controlling industrial
automation systems using industrial standards and reusable software
components.

The project builds upon existing Free Software technologies while
developing additional functionality and integrating industrial
automation technologies into a unified environment.

The project name is provisional and has not yet been established.

## Project Vision

The long-term vision is to provide a comprehensive Free Software
platform for industrial automation, accessible to developers,
engineers, educational institutions, researchers, manufacturers,
and industrial users.

The project aims to:

- Promote Free Software in industrial automation.
- Support industrial standards and interoperability.
- Reduce dependence on proprietary automation software and
  vendor-specific development environments.
- Facilitate the development of PLC applications and industrial
  control systems.
- Integrate motion control and industrial communication technologies.
- Provide an extensible foundation for HMI and SCADA applications.
- Encourage collaboration, technical knowledge sharing, and
  community-driven development.
- Preserve the freedom to study, modify, redistribute, and improve
  the software.

## Technologies and Capabilities

The project aims to integrate and extend technologies used in
industrial automation.

### PLC Programming

Development of programmable logic controller applications based
on IEC 61131-3 programming languages and standards.

The platform builds upon the existing Beremiz development
environment and related Free Software components.

### Industrial Communication

Integration of industrial communication technologies and protocols
to facilitate communication between controllers, devices, and
supervisory systems.

### EtherCAT

Support for EtherCAT-based industrial automation systems, including
master configuration, slave integration, process data exchange,
and integration with PLC applications.

The objective is to facilitate the configuration and use of
EtherCAT devices within the development environment.

### Motion Control

Integration of motion control functionality based on PLCopen
Motion Control concepts.

The project aims to provide reusable motion control function blocks
and support their integration with PLC applications and compatible
industrial drives.

### BACnet

Integration of BACnet functionality for communication with compatible
building automation and control devices.

### HMI and SCADA

Support for the development and integration of human-machine
interfaces and supervisory control and data acquisition systems.

### Future Extensions

The architecture is intended to allow additional industrial
communication protocols, control technologies, libraries, and
automation tools to be integrated as the project evolves.

The technologies listed above describe the project's scope and
development objectives. Not every capability is necessarily
complete or production-ready.

## Independence from Beremiz

This is an independent project and is not the official Beremiz
project.

It builds upon existing software and may incorporate modifications,
extensions, and integrations involving Beremiz and other Free
Software components.

The project is not affiliated with, endorsed by, or maintained
by the official Beremiz project or its maintainers.

The Beremiz name and the names of other third-party projects
remain the property of their respective rights holders.

References to existing projects are provided for identification,
technical attribution, and acknowledgment of their contributions.

## Free Software

This project is developed according to the principles of
Free Software.

Free Software is a matter of freedom, not price.

Users should have the freedom to:

- Run the software for any purpose.
- Study how the software works and modify it to meet their needs.
- Redistribute copies of the software.
- Distribute modified versions so that others can benefit from
  the improvements.

These freedoms are essential for building an independent,
transparent, and collaborative industrial automation ecosystem.

The project aims to make its original contributions available
as Free Software under the licensing terms described below.

## Licensing

### Original Contributions

Original code developed specifically for this project by its
copyright holders is intended to be distributed under the
GNU General Public License, version 3 or any later version
(GPL-3.0-or-later), provided that the relevant copyright holders
have the necessary rights to grant this license.

This statement applies only to original contributions for which
the relevant copyright holders have the authority to grant
that license.

Copyright notices and applicable license notices must be retained
as required by the licenses governing the relevant files.

### Existing Components and Third-Party Software

This project incorporates or builds upon existing software
components distributed under their respective licenses.

These components may include Beremiz, MatIEC, runtime components,
industrial communication libraries, and other third-party software.

Their applicable copyright notices, license terms, and other
obligations must be respected.

The existing Beremiz components have different licensing conditions.
The repository contains licensing information for the IDE,
Python runtime, and C++ runtime in the corresponding files:

- `COPYING_for_IDE`
- `COPYING_for_Python_Runtime`
- `COPYING_for_C_Runtime`

The presence of original contributions intended for
GPL-3.0-or-later does not automatically change the licenses
of pre-existing components.

The applicable license for each component and the distribution
requirements for combined or modified works must be determined
according to the relevant source code, copyright notices,
and license terms.

Existing license files are retained to document the applicable
licenses of the components they cover.

## Installation and Configuration

Installation and configuration procedures depend on the components
and technologies being used.

For the existing Beremiz development environment, consult its
installation instructions and documentation.

Instructions specific to this project will be added as its
development progresses.

## Development

Development focuses on extending and integrating industrial
automation capabilities while respecting applicable standards
and software licenses.

The project may include modifications to existing components,
new libraries, additional function blocks, communication
integrations, and development tools.

Contributions should follow the coding conventions and technical
requirements applicable to the relevant part of the project.

## Documentation and Technical References

The following resources document the existing Beremiz project
and may be useful when working with components incorporated
into this platform.

### Beremiz Project

- [Official Beremiz website](https://beremiz.org/)
- [Official Beremiz repository](https://github.com/beremiz/beremiz)
- [Beremiz releases](https://github.com/beremiz/beremiz/releases)
- [Beremiz documentation](https://beremiz.readthedocs.io/)
- [Beremiz installation and development instructions](doc/install.rst)
- [Beremiz YouTube channel](https://www.youtube.com/channel/UCcE4KYI0p1f6CmSwtzyg-ZA)

These links refer to the existing Beremiz project. They do not
imply that this independent project is maintained, endorsed,
or distributed by the official Beremiz project.

### Tutorials and Examples

The existing Beremiz IDE provides tutorials and examples through
the menu:

`File > Tutorials and examples`

Additional examples may be available in the repository's
`tests/projects` and `exemples` directories.

Examples inherited from existing projects remain subject to
their applicable licenses and notices.

### Documentation for Other Components

Documentation for incorporated libraries, runtimes, industrial
communication protocols, and other technologies should be consulted
according to the versions and configurations actually used.

Documentation specific to this project will be added as
features are implemented and validated.

## Contributions

Contributions, bug reports, technical discussions, and improvements
are welcome.

Contributors should ensure that they have the necessary rights
to submit their contributions under the applicable project
and component licenses.

Contributions should preserve relevant copyright notices and
respect the licenses of existing code.

## Acknowledgments

This project acknowledges the work of the developers and
communities responsible for the Free Software components
upon which it builds.

These contributions provide an important foundation for developing
and extending industrial automation technologies.

Individual components and their respective authors should be
acknowledged in accordance with their licenses and project
requirements.

## Project Status

This project is under development.

Its functionality, supported devices, integrations, documentation,
and compatibility may change as development progresses.

Users should verify the maturity and suitability of individual
features before deploying them in industrial environments.

No guarantee is made that every component is suitable for
safety-critical applications or any particular industrial use.
