from importlib.util import module_from_spec, spec_from_file_location

from setuptools import find_namespace_packages, setup

spec = spec_from_file_location("pkginfo.version", "src/version.py")
pkginfo = module_from_spec(spec)
spec.loader.exec_module(pkginfo)


with open("README.md", "r") as f:
    README = f.read()

setup(
    name=pkginfo.__packagename__,
    version=pkginfo.__version__,
    author="CMU STRUDEL",
    description="CMU-STRUDEL Variable Name Prediction Model Utilities",
    long_description=README,
    long_description_content_type="text/markdown",
    url="https://github.com/CMUSTRUDEL/DIRTY/",
    packages=find_namespace_packages("src"),
    package_dir={"": "src"},  # the root package '' corresponds to the src dir
    # include_package_data=True,
    zip_safe=False,
    install_requires=[
        "pygments~=2.9.0",
        "tqdm~=4.60.0",
        "jsonlines~=2.0.0",
        "sortedcollections~=2.1.0",
    ],
    entry_points={
        "console_scripts": [
            "csvnpm-decompiler = csvnpm.dataset_gen.generate:main",
            "csvnpm-download = csvnpm.download:main",
        ]
    },
)
