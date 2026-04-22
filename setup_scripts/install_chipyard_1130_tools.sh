#!/bin/bash


# exit script if any command fails
set -eo pipefail

error() {
    echo -e "\n\nError: $1\n\n" >&2
    exit "${2:--1}"
}

# check if thehuzz setup file is sourced
if [[ -z "${THEHUZZ_ROOT}" ]]; then
    error "thehuzz_setup.sh file is not sourced, source it: 'source <thehuzz_setup.sh file path>/thehuzz_setup.sh'"
fi

TOOLS_DIR="$THEHUZZ_ROOT/tools"
cd "$TOOLS_DIR"

echo "Installing tools into $TOOLS_DIR ..."

##############################
# install make 4.3
##############################
if [[ -d make-4.3 ]]; then
    echo "Removing existing make-4.3 ..."
    rm -rf make-4.3
fi


echo "Installing GNU Make 4.3 ..."
if [[ ! -f make-4.3.tar.gz ]]; then
    wget http://ftp.gnu.org/gnu/make/make-4.3.tar.gz
fi
tar -xvzf make-4.3.tar.gz
cd make-4.3
./configure --prefix="$(pwd)/install" 
make
make install
cd ..

# override system make with the newly installed one
export PATH="$TOOLS_DIR/make-4.3/install/bin:$PATH"
export MAKE="$TOOLS_DIR/make-4.3/install/bin/make"

echo "Using custom make from: $(command -v make)"
echo "MAKE variable set to: $MAKE"
$MAKE --version


##############################
# install jq 1.6
##############################
if [[ -d jq-1.6 ]]; then
    echo "Removing existing jq-1.6 ..."
    rm -rf jq-1.6
fi

echo "Installing jq 1.6 ..."
if [[ ! -f jq-1.6.tar.gz ]]; then
    wget https://github.com/jqlang/jq/releases/download/jq-1.6/jq-1.6.tar.gz
fi
tar -xvzf jq-1.6.tar.gz
cd jq-1.6
autoreconf -i
mkdir -p install
./configure --prefix="$(pwd)/install"
make clean
make
make install
cd ..


##############################
# install fd 7.3.0 (binary release)
##############################
if [[ -d fd-v7.3.0-x86_64-unknown-linux-musl ]]; then
    echo "Removing existing fd-v7.3.0-x86_64-unknown-linux-musl ..."
    rm -rf fd-v7.3.0-x86_64-unknown-linux-musl
fi

echo "Installing fd 7.3.0 ..."
if [[ ! -f fd-v7.3.0-x86_64-unknown-linux-musl.tar.gz ]]; then
    wget https://github.com/sharkdp/fd/releases/download/v7.3.0/fd-v7.3.0-x86_64-unknown-linux-musl.tar.gz
fi
tar -xvzf fd-v7.3.0-x86_64-unknown-linux-musl.tar.gz


##############################
# install JDK 8u412 (Adoptium)
##############################
if [[ -d jdk8u412-b08 ]]; then
    echo "Removing existing jdk8u412-b08 ..."
    rm -rf jdk8u412-b08
fi

echo "Installing OpenJDK 8 (Adoptium) ..."
if [[ ! -f OpenJDK8U-jdk_x64_linux_hotspot_8u412b08.tar.gz ]]; then
    wget https://github.com/adoptium/temurin8-binaries/releases/download/jdk8u412-b08/OpenJDK8U-jdk_x64_linux_hotspot_8u412b08.tar.gz
fi
tar -xvzf OpenJDK8U-jdk_x64_linux_hotspot_8u412b08.tar.gz


##############################
# install ninja 1.11.1
##############################
if [[ -f ninja ]]; then
    echo "Removing existing ninja ..."
    rm -f ninja
fi

echo "Installing Ninja 1.11.1 ..."
if [[ ! -f ninja-linux.zip ]]; then
    curl -LO https://github.com/ninja-build/ninja/releases/download/v1.11.1/ninja-linux.zip
fi
unzip -o ninja-linux.zip
chmod +x ninja



##############################
# installing verilator
##############################

# === Install gdown if missing ===
if ! command -v gdown &> /dev/null; then
    echo "gdown not found, installing..."
    python3 -m pip install --user --quiet gdown
    export PATH="$HOME/.local/bin:$PATH"
fi

# === Download verilator.zip if not already present ===
if [[ ! -f verilator.zip ]]; then
    echo "Downloading verilator.zip..."
    gdown --id 1ZiW4hw-pqqtWI2WPNxxUfhJDDQrgIhga -O verilator.zip
else
    echo "verilator.zip already exists, skipping download."
fi

# === Unzip into verilator/ directory ===
if [[ ! -d verilator ]]; then
    echo "Extracting verilator.zip..."
    unzip -q verilator.zip -d verilator
else
    echo "verilator/ directory already exists, skipping extraction."
fi




echo "===================================================="
echo "All tools installed in $TOOLS_DIR"
