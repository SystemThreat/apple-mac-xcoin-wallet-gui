# The native keytool (xcoin-wallet / xcoin-wallet.exe) on macOS, Linux and Windows, from the vendored PQClean
# sources: ML-DSA-65 (FIPS 204) and SLH-DSA-SHA2-128s (FIPS 205), the files the node compiles. build.sh stays the
# one-command build on a Mac; CI and the Windows app build with:
#
#   cmake -S . -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build --config Release && ctest --test-dir build -C Release
cmake_minimum_required(VERSION 3.16)
project(xcoin_wallet C CXX)
set(CMAKE_C_STANDARD 99)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")   # static runtime: no VC++ redistributable needed
  add_compile_definitions(_CRT_SECURE_NO_WARNINGS)
endif()

set(PQ ${CMAKE_SOURCE_DIR}/pqcrypto)
# ml-dsa-65 and slh-dsa-sha2-128s share file names (sign.c, params.h, api.h): each compiles with only its own headers.
add_library(pq_common OBJECT ${PQ}/common/fips202.c ${PQ}/common/sha2.c ${PQ}/common/cleanse.c ${CMAKE_SOURCE_DIR}/randombytes.c)
target_include_directories(pq_common PRIVATE ${PQ}/common)
file(GLOB MLDSA_SRC ${PQ}/ml-dsa-65/*.c)
add_library(pq_mldsa OBJECT ${MLDSA_SRC})
target_include_directories(pq_mldsa PRIVATE ${PQ}/common ${PQ}/ml-dsa-65)
file(GLOB SLH_SRC ${PQ}/slh-dsa-sha2-128s/*.c)
add_library(pq_slh OBJECT ${SLH_SRC})
target_include_directories(pq_slh PRIVATE ${PQ}/common ${PQ}/slh-dsa-sha2-128s)

add_executable(xcoin-wallet xcoin-wallet.cpp $<TARGET_OBJECTS:pq_common> $<TARGET_OBJECTS:pq_mldsa> $<TARGET_OBJECTS:pq_slh>)
target_include_directories(xcoin-wallet PRIVATE ${PQ}/common)
if(WIN32)
  target_link_libraries(xcoin-wallet PRIVATE bcrypt)
endif()

# A build is only good if it still speaks the chain's witness v3 byte language (the node's golden vectors).
enable_testing()
add_test(NAME v3vectors COMMAND xcoin-wallet _v3vectors)
