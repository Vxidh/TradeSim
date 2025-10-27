from setuptools import setup, Extension
import pybind11
import glob
import os # <-- We need this!

# Find all .cpp files in the engine/ directory
cpp_files = glob.glob('engine/*.cpp')

# This is the key change for Windows:
# We use /std:c++17 instead of -std=c++17
compile_args = []
if os.name == 'nt': # 'nt' is the name for Windows
    compile_args = ['/std:c++17']
else:
    compile_args = ['-std=c++17']

ext_modules = [
    Extension(
        'tradesim_engine',  # The name of the Python module
        cpp_files,          # List of source files
        include_dirs=[
            pybind11.get_include(),
            'engine/', # So OrderBook.cpp can find Order.h
        ],
        language='c++',
        extra_compile_args=compile_args, # Use the correct args here
    ),
]

setup(
    name='tradesim_engine',
    version='1.0.0',
    author='Your Name',
    description='TradeSim C++ Matching Engine',
    ext_modules=ext_modules,
)