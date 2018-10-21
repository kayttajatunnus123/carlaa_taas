# Use official Python runtime on debian-stretch-slim
FROM python:2.7-slim

# Set the working directory to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Make folder for saving the videos. A volume can be mounted here
RUN mkdir /app/output

# Install ffmpeg for video encoding
RUN apt-get -qq update && apt-get -qq install -y ffmpeg

# Run client when the container launches
CMD ["python", "client.py", "--verbose", "--host", "10.0.2.2", "--port", "20000", "--autopilot"]
