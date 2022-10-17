ARG BUILD_FROM
ARG BUILD_ARCH

FROM $BUILD_FROM
LABEL maintainer="kastbernd@gmx.de"

USER root
COPY requirements.txt /
COPY tesla_pv.py /

RUN python -m pip install --user -r /requirements.txt
ENV PYTHONUNBUFFERED="TRUE"
CMD ["python3", "-u", "/tesla_pv.py"]
