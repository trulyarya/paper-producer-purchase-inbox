# Use the official Python slim image as a base
FROM python:3.13.9-slim

# system dependencies the Azure-CLI wheels expect
# install dependencies and clean up apt cache
# the reason we do this is because the azure-cli package has some compiled components

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libffi-dev libssl-dev libxml2 libxslt1.1 \
      gcc curl ca-certificates \
      libcairo2 \
      libpango-1.0-0 \
      libpangoft2-1.0-0 \
      libpangocairo-1.0-0 \
      libgdk-pixbuf-2.0-0 \
      libglib2.0-0 \
      fonts-dejavu fonts-liberation fonts-noto-color-emoji \
 && rm -rf /var/lib/apt/lists/*

# drop Azure CLI into an isolated virtualenv
RUN python -m venv /opt/azcli \
 && /opt/azcli/bin/pip install --upgrade pip \
 && /opt/azcli/bin/pip install azure-cli==2.78.0 \
 && ln -s /opt/azcli/bin/az /usr/local/bin/az

# Set working directory 
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install dependencies
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy application code to the container
COPY . .

# Command to run the application, exposing it to all network interfaces
CMD ["python", "src/workflow/workflow.py", "--host", "0.0.0.0", "--port", "80", "--reload"]


# run this in terminal to build the docker image:
# docker build -t papercoapp .

# run this in terminal to run the docker image:
# docker run --name paperco-container -p 80:80 papercoapp

# run this in terminal to enter the running container (dns for internet access):
# docker run --rm -it --dns 1.1.1.1 papercoapp /bin/bash
















# FROM mcr.microsoft.com/azure-cli:2.63.0 AS azcli

# FROM python:3.13.9-slim
# COPY --from=azcli /usr/bin/az /usr/bin/az
# COPY --from=azcli /usr/lib/azure-cli /usr/lib/azure-cli
# COPY --from=azcli /opt/az /opt/az
# ENV PATH=/opt/az/bin:$PATH


# # FROM python:3.13-slim

# WORKDIR /app

# COPY ./requirements.txt ./
# RUN pip install --no-cache-dir -r requirements.txt

# COPY . .

# CMD ["python", "src/workflow/workflow.py", "--host", "0.0.0.0", "port", "80", "--reload"]







# FROM mcr.microsoft.com/azure-cli:2.63.0
# RUN apt-get update && apt-get install -y python3 python3-pip && rm -rf /var/lib/apt/lists/*
# WORKDIR /app
# COPY requirements.txt .
# RUN pip install --no-cache-dir -r requirements.txt
# COPY . .
# CMD ["python3", "src/workflow/workflow.py", "--host", "0.0.0.0", "port", "80", "--reload"]
