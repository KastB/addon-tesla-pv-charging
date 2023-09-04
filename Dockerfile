ARG BUILD_FROM
ARG BUILD_ARCH

FROM $BUILD_FROM
LABEL maintainer="kastbernd@gmx.de"

USER root
RUN apt-get update && apt-get install -y python3 python3-dev gcc \
    gfortran musl-dev \
    libffi-dev
COPY requirements.txt /
COPY tesla_pv.py /

RUN python -m pip install --user -r /requirements.txt
ENV PYTHONUNBUFFERED="TRUE"
CMD ["python3", "-u", "/tesla_pv.py"]
