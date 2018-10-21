#!/usr/bin/env python

# A demonstrator Carla client system for the course CS-C3140 Operating systems
# Based on a pygame manual control client version, see licence below.

# Copyright (c) 2017 Computer Vision Center (CVC) at the Universitat Autonoma de
# Barcelona (UAB).
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

# Keyboard controlling for CARLA. Please refer to client_example.py for a simpler
# and more documented example.

"""
Welcome to CARLA.

STARTING in a moment...
"""

from __future__ import print_function

import sys

sys.path.append(
    'carla-0.9.0-py%d.%d-linux-x86_64.egg' % (sys.version_info.major,
                                                        sys.version_info.minor))

import carla

import argparse
import logging
import random
import time
import signal

import subprocess as sp
import threading as th

WINDOW_WIDTH = 320
WINDOW_HEIGHT = 240
START_POSITION = carla.Transform(carla.Location(x=180.0, y=199.0, z=40.0))
CAMERA_POSITION = carla.Transform(carla.Location(x=0.5, z=1.40))

BITRATE = '1000k'
BUFSIZE = '5000k'
FPS = 25
CORRECTION = 0.001
FPS_SLEEP = 1.0 / FPS - CORRECTION


COMMAND = ["ffmpeg",
        '-loglevel', 'debug',
        '-f', 'rawvideo',
        '-vcodec', 'rawvideo',
        '-s', '{:d}x{:d}'.format(WINDOW_WIDTH, WINDOW_HEIGHT),
        '-pix_fmt', 'bgra',
        '-r', "{:d}".format(FPS),
        '-i', '-',
        '-vcodec', 'libx264',
        '-an',
        '-crf', '23',
        '-preset', 'fast',
        '-minrate', BITRATE,
        '-maxrate', BITRATE,
        '-b:v', BITRATE,
        '-bufsize', BUFSIZE,
        '-deinterlace',
        '-vf', "fps=fps={:d}".format(FPS),
        '-r', "{:d}".format(FPS),
        '-g', "{:d}".format(FPS/2),
        '-keyint_min',"{:d}".format(FPS/2),
        '-pix_fmt', 'yuv420p',
        '-movflags', 'faststart',
        '-f', 'mp4', time.strftime('output/carla_client-%m%d%H%M%S.mp4', time.gmtime())
        ]

class CarlaGame(object):
    def __init__(self, args):
        self._client = carla.Client(args.host, args.port)
        self._client.set_timeout(10.0)
        self._display = None
        self._surface = None
        self._camera = None
        self._vehicle = None
        self._autopilot_enabled = args.autopilot
        self._is_on_reverse = False
        self._frame_time = None
        self._prev_frame_number = 0
        self._prev_fps = 0
        self._prev_server_fps = 0
        self._prev_print = 0
        self._last_toggle = 0
        self._image = None
        self._image2 = None
        self._firstimage = False
        self._pipe = None
        self._continuepipe = True
        signal.signal(signal.SIGTERM, self._exit_ffmpeg)

    def execute(self):
        try:
            logging.debug('pygame started')

            world = self._client.get_world()
            blueprint = random.choice(world.get_blueprint_library().filter('vehicle'))
            self._vehicle = world.spawn_actor(blueprint, START_POSITION)
            self._vehicle.set_autopilot(self._autopilot_enabled)
            cam_blueprint = world.get_blueprint_library().find('sensor.camera.rgb')
            cam_blueprint.set_attribute('image_size_x', str(WINDOW_WIDTH))
            cam_blueprint.set_attribute('image_size_y', str(WINDOW_HEIGHT))
            self._camera = world.spawn_actor(cam_blueprint, CAMERA_POSITION, attach_to=self._vehicle)
            self._frame_time = time.time()
            self._camera.listen(self._parse_image)
            self._pipe = sp.Popen( COMMAND, stdin=sp.PIPE )
            pipethread = th.Thread( target=self._send_to_pipe )
            pipethread.start()
            
            while True:
                self._on_loop()

            self._continuepipe = False
        finally:
            if self._camera is not None:
                self._camera.destroy()
                self._camera = None
            if self._vehicle is not None:
                self._vehicle.destroy()
                self._vehicle = None
            self._continuepipe = False

    def _parse_image(self, image):
        if self._firstimage:
            self._image2 = image.raw_data
            self._firstimage = False
        else:
            self._image = image.raw_data
            self._firstimage = True
        current_time = time.time()
        skipped_frames = image.frame_number - self._prev_frame_number
        self._prev_frame_number = image.frame_number
        self._prev_fps = 1.0 / (current_time - self._frame_time)
        self._prev_server_fps = skipped_frames / (current_time - self._frame_time) 
        self._frame_time = current_time

    def _on_loop(self):
        autopilot = self._autopilot_enabled
        control = carla.VehicleControl()
        control.reverse = self._is_on_reverse
        self._last_toggle = time.time()
        if autopilot != self._autopilot_enabled:
            self._vehicle.set_autopilot(self._autopilot_enabled)
        if not self._autopilot_enabled:
            self._vehicle.apply_control(control)
            
        if time.time() - self._prev_print > 1:
            self._prev_print = time.time()
            self._print_statistics()

    def _send_to_pipe(self):
        while not self._firstimage:
            time.sleep(FPS_SLEEP)
        while self._continuepipe:
            prevpipe = time.time()
            if self._firstimage:
                self._pipe.stdin.write( self._image )
            else:
                self._pipe.stdin.write( self._image2 )
            wait = FPS_SLEEP - (time.time() - prevpipe)
            if wait > 0:
                time.sleep(wait)

    def _print_statistics(self):
        print("FPS: ", self._prev_fps)
        print("Server FPS: ", self._prev_server_fps)
        send_time = time.time()
        self._client.ping()
        receive_time = time.time()
        latency = receive_time - send_time
        print("Round trip time: ", latency)

    def _exit_ffmpeg(self, signum, frame):
        self._pipe.send_signal(signal.SIGINT)
        self._continuepipe = False
        time.sleep(5)
        self._pipe.send_signal(signal.SIGKILL)
        sys.exit()


def main():
    argparser = argparse.ArgumentParser(
        description='CARLA Manual Control Client')
    argparser.add_argument(
        '-v', '--verbose',
        action='store_true',
        dest='debug',
        help='print debug information')
    argparser.add_argument(
        '--host',
        metavar='H',
        default='localhost',
        help='IP of the host server (default: localhost)')
    argparser.add_argument(
        '-p', '--port',
        metavar='P',
        default=2000,
        type=int,
        help='TCP port to listen to (default: 2000)')
    argparser.add_argument(
        '-a', '--autopilot',
        action='store_true',
        help='enable autopilot')
    args = argparser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(format='%(levelname)s: %(message)s', level=log_level)

    logging.info('listening to server %s:%s', args.host, args.port)

    print(__doc__)

    while True:
        try:
            game = CarlaGame(args)
            game.execute()
            break

        except Exception as error:
            logging.error(error)
            time.sleep(1)


if __name__ == '__main__':

    try:
        main()
    except KeyboardInterrupt:
        print('\nCancelled by user. Bye!')
