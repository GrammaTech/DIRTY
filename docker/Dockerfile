#######################################
# test image
#######################################
FROM ubuntu:18.04 as test

ENV LANG=C.UTF-8 LC_ALL=C.UTF-8
ENV PATH /opt/conda/bin:$PATH

# aptitude package retrieval
RUN apt-get update --fix-missing
RUN apt-get install -y \
        manpages-dev \
        manpages-posix-dev
RUN apt-get install -y \
        wget \
        bzip2 \
        ca-certificates \
        libglib2.0-0 \
        libxext6 \
        libsm6 \
        libxrender1 \
        git \
        mercurial \
        subversion
RUN apt-get install -y \
        gcc \
        g++ \
        make
RUN apt-get clean

# conda retrieval
RUN wget --quiet https://repo.anaconda.com/archive/Anaconda3-2020.11-Linux-x86_64.sh -O ~/anaconda.sh && \
    /bin/bash ~/anaconda.sh -b -p /opt/conda && \
    rm ~/anaconda.sh && \
    ln -s /opt/conda/etc/profile.d/conda.sh /etc/profile.d/conda.sh && \
    echo ". /opt/conda/etc/profile.d/conda.sh" >> ~/.bashrc && \
    echo "conda activate base" >> ~/.bashrc && \
    find /opt/conda/ -follow -type f -name '*.a' -delete && \
    find /opt/conda/ -follow -type f -name '*.js.map' -delete && \
    /opt/conda/bin/conda clean -afy

RUN chown -R 10023:10 /opt/conda/

CMD [ "/bin/bash" ]