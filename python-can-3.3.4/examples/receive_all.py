#!/usr/bin/env python

from __future__ import print_function

import can
from can.bus import BusState


def receive_all():
    print('Open BUSMUST CAN channel using 500kbps baudrate ...')
    bus = can.interface.Bus(bustype='bmcan', channel=0, bitrate=500000, data_bitrate=2000000, tres=True)
    #bus = can.interface.Bus(bustype='pcan', channel='PCAN_USBBUS1', bitrate=250000)
    #bus = can.interface.Bus(bustype='ixxat', channel=0, bitrate=250000)
    #bus = can.interface.Bus(bustype='vector', app_name='CANalyzer', channel=0, bitrate=250000)

    bus.state = BusState.ACTIVE  # or BusState.PASSIVE

    print('Waiting for RX CAN messages ...')
    try:
        while True:
            msg = bus.recv(1)
            if msg is not None:
                print(msg)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    receive_all()
