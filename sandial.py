# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function
import threading
from time import sleep
import datetime
import codecs

__author__ = 'ethan'

codecs.register(codecs.lookup)  # Fix LookupError thread race condition


class MovingLockoutError(IOError):
    pass


class HeartbeatSync(object):
    def __init__(self):
        self.next_heartbeat = None
        self.beat_tdelta = datetime.timedelta(microseconds=50000)
        self.beat_sleep = self.beat_tdelta.seconds + (self.beat_tdelta.microseconds / 1000000.0)

    def heartbeat_sync(self):
        my_now = datetime.datetime.now()
        my_now_dummy = datetime.datetime.now()
        if self.next_heartbeat is None:
            self.next_heartbeat = my_now + self.beat_tdelta
            # do the same ops so it takes the same time
            time_diff = self.next_heartbeat - my_now_dummy
            wait_time = time_diff.seconds + (time_diff.microseconds / 1000000.0)
            wait_time_log = unicode(repr(wait_time))
            sleep(self.beat_sleep)
        else:
            time_diff = self.next_heartbeat - my_now
            wait_time = time_diff.seconds + (time_diff.microseconds / 1000000.0)
            wait_time_log = unicode(repr(wait_time))
            print(wait_time_log)
            sleep(wait_time)
            self.next_heartbeat = None


class BuddySync(object):
    def __init__(self, req_buddies=2, default_timeout=5):
        self.req_buddies = req_buddies
        self.default_timeout = default_timeout
        self.cur_buddies = 0
        self.evt_go = threading.Event()

    def buddy_up(self):
        if self.cur_buddies == (self.req_buddies - 1):
            self._flush_buddies()
        else:
            self.cur_buddies += 1
            self._wait_for_buddy()

    def _flush_buddies(self):
        self.evt_go.set()
        self.cur_buddies = 0
        self.evt_go.clear()

    def _wait_for_buddy(self):
        self.evt_go.wait(self.default_timeout)


class SketchController(object):
    DEFAULT_V = 3

    def __init__(self):
        self.threads = []
        self._x_lock = threading.Lock()
        self._y_lock = threading.Lock()
        self.x = 0.0
        self.y = 0.0
        self.heartbeat = HeartbeatSync()
        self.buddysync = BuddySync()
        self.x_move_ts = None
        self.y_move_ts = None

    def shake_to_clear(self):
        raise NotImplementedError

    def return_to_origin(self):
        raise NotImplementedError

    def print_move_deltas(self):
        move_delta = self.y_move_ts - self.x_move_ts
        if move_delta.days < 0:
            move_delta2 = datetime.timedelta(days=0) - move_delta
            delta_log = "x --> -{}s --> y".format(move_delta2.seconds + (move_delta2.microseconds / 1000000.0))
        else:
            delta_log = "x --> +{}s --> y".format(move_delta.seconds + (move_delta.microseconds / 1000000.0))
        print(delta_log)

    def _move_x(self, v_x, t):
        # self.heartbeat.heartbeat_sync()
        self.buddysync.buddy_up()
        move_ts = datetime.datetime.now()
        self.x_move_ts = move_ts

        # print("starting _move_x {}\n".format(move_ts))
        print("starting _move_x {}\n".format(move_ts))
        sleep(t)
        print("done _move_x {}\n".format(datetime.datetime.now()))
        if self.x_move_ts and self.y_move_ts:
            self.print_move_deltas()
        # TODO: implement the motion

    def move_x(self, delta_x, delta_t=0.5):
        calc_vx = float(delta_x) / float(delta_t)

        with self._x_lock:
            self._move_x(calc_vx, delta_t)
            self.x += delta_x

    def _move_y(self, v_y, t):
        # self.heartbeat.heartbeat_sync()
        self.buddysync.buddy_up()
        move_ts = datetime.datetime.now()
        self.y_move_ts = move_ts
        print("starting _move_y {}\n".format(move_ts))
        sleep(t)
        print("done _move_y {}\n".format(datetime.datetime.now()))
        if self.x_move_ts and self.y_move_ts:
            self.print_move_deltas()
        # TODO: implement the motion

    def move_y(self, delta_y, delta_t=0.5):
        calc_vy = float(delta_y) / float(delta_t)

        with self._y_lock:
            self._move_y(calc_vy, delta_t)
            self.y += delta_y

    def move_x_and_y(self, delta_x, delta_y, delta_t=0.5):
        calc_vx = float(delta_x) / float(delta_t)
        calc_vy = float(delta_y) / float(delta_t)

        with self._x_lock:
            with self._y_lock:
                # Kudos to http://stackoverflow.com/a/12376400/4437749
                t1 = threading.Thread(target=self._move_x, args=(calc_vx, delta_t))
                t2 = threading.Thread(target=self._move_y, args=(calc_vy, delta_t))
                # Make threads daemonic, i.e. terminate them when main thread
                # terminates. From: http://stackoverflow.com/a/3788243/145400
                t1.daemon = True
                t2.daemon = True
                t1.start()
                t2.start()
                self.threads.append(t1)
                self.threads.append(t2)

    @property
    def position(self):
        return self.x, self.y


def join_threads(threads):
    """
    Join threads in interruptable fashion.
    From http://stackoverflow.com/a/9790882/145400
    """
    for t in threads:
        while t.isAlive():
            t.join(5)


class ClockSketch(object):
    def __init__(self):
        self.width = 600
        self.height = 600


def main():

    try:
        sc = SketchController()
        sc.move_x_and_y(5.3, 7.9, 0.1)
        join_threads(sc.threads)
    except KeyboardInterrupt:
        print("\nKeyboardInterrupt catched.")
        print("Terminate main thread.")
        print("If only daemonic threads are left, terminate whole program.")
        exit(1)

if __name__ == '__main__':
    main()
