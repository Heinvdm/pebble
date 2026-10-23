#!/usr/bin/env bash
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
sdk="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-$LOCALAPPDATA/Android/Sdk}}"
sdk="$(cd "$sdk" && pwd)"
ndk_version="${PEBBLE_NDK:-28.2.13676358}"
cmake_version="${PEBBLE_CMAKE:-3.31.6}"
tag="${PEBBLE_LLAMA_TAG:-v0.6.0}"
ndk="$sdk/ndk/$ndk_version"
cmake_bin="$sdk/cmake/$cmake_version/bin"
src="$here/src"
out="$here/out/jniLibs"
abis="${*:-arm64-v8a x86_64}"

if [ ! -d "$ndk" ]; then
  echo "NDK $ndk_version is missing: sdkmanager --install \"ndk;$ndk_version\"" >&2
  exit 1
fi
if [ ! -x "$cmake_bin/cmake" ] && [ ! -x "$cmake_bin/cmake.exe" ]; then
  echo "CMake $cmake_version is missing: sdkmanager --install \"cmake;$cmake_version\"" >&2
  exit 1
fi
if [ ! -d "$src" ]; then
  git clone --depth 1 --branch "$tag" https://github.com/ggml-org/llama.cpp.git "$src"
fi
export PATH="$cmake_bin:$PATH"

for abi in $abis; do
  build="$here/build/$abi"
  cmake -S "$src" -B "$build" -G Ninja \
    -DCMAKE_MAKE_PROGRAM="$cmake_bin/ninja" \
    -DCMAKE_TOOLCHAIN_FILE="$ndk/build/cmake/android.toolchain.cmake" \
    -DANDROID_ABI="$abi" \
    -DANDROID_PLATFORM=android-29 \
    -DANDROID_STL=c++_static \
    -DCMAKE_BUILD_TYPE=Release \
    -DBUILD_SHARED_LIBS=ON \
    -DGGML_BACKEND_DL=ON \
    -DGGML_CPU_ALL_VARIANTS=ON \
    -DGGML_NATIVE=OFF \
    -DGGML_OPENMP=OFF \
    -DGGML_LLAMAFILE=OFF \
    -DGGML_CCACHE=OFF \
    -DLLAMA_OPENSSL=OFF \
    -DLLAMA_BUILD_IS_DEV=OFF \
    -DLLAMA_BUILD_TESTS=OFF \
    -DLLAMA_BUILD_EXAMPLES=OFF \
    -DLLAMA_BUILD_APP=OFF \
    -DLLAMA_BUILD_TOOLS=ON \
    -DLLAMA_BUILD_SERVER=ON \
    -DCMAKE_BUILD_RPATH='$ORIGIN' \
    -DCMAKE_INSTALL_RPATH='$ORIGIN' \
    -DCMAKE_SHARED_LINKER_FLAGS="-Wl,-z,max-page-size=16384" \
    -DCMAKE_EXE_LINKER_FLAGS="-Wl,-z,max-page-size=16384"
  variants=$(cmake --build "$build" --target help | sed -n 's/^\(ggml-cpu-[A-Za-z0-9_.-]*\):.*/\1/p' | sort -u | tr '\n' ' ')
  cmake --build "$build" --target llama-server $variants
  rm -rf "${out:?}/$abi"
  mkdir -p "$out/$abi"
  strip="$(ls -d "$ndk"/toolchains/llvm/prebuilt/*/bin | head -n 1)/llvm-strip"
  find "$build/bin" -maxdepth 1 -name "lib*.so" -exec cp {} "$out/$abi/" \;
  cp "$build/bin/llama-server" "$out/$abi/libllama-server.so"
  for lib in "$out/$abi"/*.so; do
    "$strip" --strip-unneeded "$lib"
  done
  ls -l "$out/$abi"
done
echo "llama.cpp $tag built into $out"
