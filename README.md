# CVA6 RISC-V Processor

This project aims to analyze [CVA6](https://github.com/openhwgroup/cva6), a 64-bit, 6-stage RISC-V architecture processor developed in the hardware description language **SystemVerilog**.

This project uses [Docker](https://www.docker.com/) to avoid installing all of CVA6's dependencies on the host OS and to ensure portability. A Docker image with all the necessary tools to work with the processor is provided.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Docker Setup](#docker-setup)
  - [Installing Docker](#installing-docker)
  - [Enabling Graphical Applications](#enabling-graphical-applications)
  - [Optional Configuration](#optional-configuration)
  - [Managing the Docker Service](#managing-the-docker-service)
- [Working with the CVA6 Image](#working-with-the-cva6-image)
  - [Downloading the Image](#downloading-the-image)
  - [Creating the Container](#creating-the-container)
  - [Starting and Stopping the Container](#starting-and-stopping-the-container)
- [Running Tests](#running-tests)
  - [First Assembly Test](#first-assembly-test)
  - [First C Test](#first-c-test)
  - [Running Custom Assembly Programs](#running-custom-assembly-programs)
  - [Running Custom C Programs](#running-custom-c-programs)
  - [Limitations and Considerations](#limitations-and-considerations)
- [Building Your Own Docker Image](#building-your-own-docker-image)

---

## Prerequisites

Before starting, make sure you have:

- A **Linux Debian** operating system (or a Debian-based distribution such as Ubuntu).
- An **AMD account** (required only if you plan to install Vivado).
- Sufficient disk space for the Docker image and, optionally, the Vivado toolchain.

---

## Docker Setup

### Installing Docker

To install the tool, run the following commands:

```bash
sudo apt-get update
sudo apt-get install -y docker.io
```

Verify it was installed correctly:

```bash
sudo docker version
```

### Enabling Graphical Applications

To run graphical applications from inside the container, run the following commands:

```bash
xhost +
socat TCP-LISTEN:6000,reuseaddr,fork UNIX-CLIENT:/tmp/.X11-unix/X0
```

### Optional Configuration

The following steps are recommended to make working with Docker easier.

#### Start Docker automatically on boot

```bash
sudo systemctl enable docker
```

#### Run Docker commands without `sudo`

Replace `<user_name>` with your system username (you can get it by running `whoami`).

```bash
sudo groupadd docker
sudo usermod -aG docker <user_name>
newgrp docker
```

Then run the following command, which should not require `sudo`:

```bash
docker run hello-world
```

#### Access container contents from VSCode

To access the container's contents from VSCode, install the `Docker` extension from the `Extensions` panel.

### Managing the Docker Service

Start the service:

```bash
sudo systemctl start docker
```

Verify it started correctly:

```bash
sudo systemctl status docker
```

To stop the service, run:

```bash
sudo systemctl stop docker
```

---

## Working with the CVA6 Image

### Downloading the Image

Go to [Docker Hub](https://hub.docker.com/r/manuel313/cva6/tags) to check the most up-to-date image tag and pull it:

```bash
docker pull manuel313/cva6:latest>
```

Verify it was downloaded correctly:

```bash
docker images
```

### Creating the Container

Create a container named `<container_name>` that will be operated through a Bash terminal and will have permission to run graphical applications (replace `<container_name>` with the desired container name):

```bash
docker run -it --name <container_name> -e DISPLAY=$DISPLAY -v /tmp/.X11-unix:/tmp/.X11-unix manuel313/cva6:latest bash
```

To exit the container, run the following command from inside its terminal:

```bash
exit
```

### Starting and Stopping the Container

Once the container has been created, to start it run:

```bash
docker start <container_name>
```

To enter the container, run:

```bash
docker exec -e DISPLAY=host.docker.internal:0 -it <container_name> bash
```

To exit the container, run from inside its terminal:

```bash
exit
```

To stop the container, run:

```bash
docker stop <container_name>
```

---

## Running Tests

It is recommended to compile the C program before running it. To do so, you can use the following command (replacing `<program_name>` with the name of the `.c` file and `<executable_name>` with the desired name for the executable):

```bash
gcc -Wall -Wextra -O3 -g -std=c99 -o <executable_name> <program_name>
./<executable_name>
```

### Limitations and Considerations

**C programs:**

- Only the libraries `stdio.h`, `stdint.h`, and `string.h` are available.
- The functions `malloc` and `free` cannot be used.

**`veri-testharness` simulator:**

- The processor can only run for 2 million cycles or 500 seconds, whichever comes first.

---

## Building Your Own Docker Image

If you want to create a Docker image with the basic tools to work with the processor, follow the steps below.

**1. Build the base image.** From the project's root folder, run the following command (replacing `<username>` and `<tag>` with the desired values):

```bash
docker build -t <username>/cva6:<tag> .
```

**2. Create a container from the new image.** Follow the steps detailed in the [Creating the Container](#creating-the-container) and [Starting and Stopping the Container](#starting-and-stopping-the-container) sections.

**3. Configure the environment inside the container.** Once inside, run the following sequence of commands:

```bash
source verif/sim/setup-env.sh
export DV_SIMULATORS=veri-testharness
bash verif/regress/smoke-tests-cv64a6_imafdc_sv39.sh
```

It is recommended to run the `hello_world.c` and `custom_test_template.S` programs as detailed in the [Running Tests](#running-tests) section to verify that the environment has been configured correctly.

**4. Commit the container as a new image.** Exit the container without closing it. Once outside, create an image from the modified container by running the following command (replacing `<username>` and `<tag>` with the previous values and `<container_name>` with the container's name):

```bash
docker commit <container_name> <username>/cva6:<tag>
```

Verify the image was created correctly:

```bash
docker images
```