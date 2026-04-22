# Chipyard tools setup
# comment out git for olympus

# GNU Make 4.3
if [[ -x "$THEHUZZ_ROOT/tools/make-4.3/install/bin/make" ]]; then
    export PATH="$THEHUZZ_ROOT/tools/make-4.3/install/bin:$PATH"
    export MAKE="$THEHUZZ_ROOT/tools/make-4.3/install/bin/make"
fi

# fd
if [[ -x "$THEHUZZ_ROOT/tools/fd-v7.3.0-x86_64-unknown-linux-musl/fd" ]]; then
    export PATH="$THEHUZZ_ROOT/tools/fd-v7.3.0-x86_64-unknown-linux-musl:$PATH"
fi

# jq
if [[ -x "$THEHUZZ_ROOT/tools/jq-1.6/install/bin/jq" ]]; then
    export PATH="$THEHUZZ_ROOT/tools/jq-1.6/install/bin:$PATH"
fi

# JDK
if [[ -x "$THEHUZZ_ROOT/tools/jdk8u412-b08/bin/javac" ]]; then
    export PATH="$THEHUZZ_ROOT/tools/jdk8u412-b08/bin:$PATH"
fi

# Ninja
if [[ -x "$THEHUZZ_ROOT/tools/ninja" ]]; then
    export PATH="$THEHUZZ_ROOT/tools:$PATH"
fi

# Verilator

if [[ -x "$THEHUZZ_ROOT/tools/verilator" ]]; then
    export PATH=$THEHUZZ_ROOT/tools/verilator/verilator/bin:$PATH
    export VERILATOR_ROOT=$THEHUZZ_ROOT/tools/verilator/verilator
fi


export CHIPYARD_TOOLS_SOURCED=1
