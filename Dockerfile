ARG BUILD_FROM
ARG BUILD_ARCH

FROM $BUILD_FROM
LABEL maintainer="kastbernd@gmx.de"

USER root
COPY requirements.txt /
COPY tesla_pv.py /

RUN python -m pip install --user -r /requirements.txt

CMD ["python3", "/tesla_pv.py"]
