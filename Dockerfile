FROM python:3.11-slim

RUN apt update && apt install -y wget zip

RUN wget https://github.com/projectdiscovery/subfinder/releases/download/v2.9.0/subfinder_2.9.0_linux_amd64.zip -O subfinder_linux_amd64.zip &&\
    unzip subfinder_linux_amd64.zip && mv subfinder /usr/local/bin/

COPY . .

RUN pip install -e .
RUN playwright install --with-deps chromium

ENTRYPOINT [ "snaprecon" ]