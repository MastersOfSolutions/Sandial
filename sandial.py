# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function
import threading
from time import sleep
import datetime
import codecs
from collections import deque
import math

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
        self.threads = deque()
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
        calc_delta_x = v_x * t
        self.x += calc_delta_x
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
        calc_delta_y = v_y * t
        self.y += calc_delta_y
        # TODO: implement the motion

    def move_y(self, delta_y, delta_t=0.5):
        calc_vy = float(delta_y) / float(delta_t)

        with self._y_lock:
            self._move_y(calc_vy, delta_t)
            self.y += delta_y

    def move_x_and_y(self, delta_x, delta_y, delta_t=0.2):
        calc_vx = float(delta_x) / float(delta_t)
        calc_vy = float(delta_y) / float(delta_t)
        old_x, old_y = self.x, self.y

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

        self.wait_in_line()
        print("({},{}) --> ({},{})\n".format(old_x, old_y, self.x, self.y))

    def wait_in_line(self):
        for t in self.threads:
            while t.isAlive():
                t.join(5)
        self.threads.clear()

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
    def __init__(self, sketch_controller):
        self.origin_x = 0.0
        self.origin_y = 0.0
        self.width = 600.0
        self.height = 600.0
        self.tick_len = 20.0
        self.mid_x = (self.width / 2.0) + self.origin_x
        self.mid_y = (self.height / 2.0) + self.origin_y
        assert isinstance(sketch_controller, SketchController)
        self.sc = sketch_controller
        assert isinstance(self.sc, SketchController)
        self.refresh_clock()

    def reset(self):
        delta_x_orig = self.origin_x - self.sc.x
        delta_y_orig = self.origin_y - self.sc.y
        self.sc.move_x_and_y(delta_x_orig, delta_y_orig)
        # TODO: self.sc.shake_to_clear()

    def paint_clockface(self):
        self.sc.move_x_and_y(self.mid_x, 0.0)
        self.sc.move_x_and_y(0.0, self.tick_len)
        self.sc.move_x_and_y(0.0, -self.tick_len)
        self.sc.move_x_and_y(self.mid_x, 0.0)
        self.sc.move_x_and_y(0.0, self.mid_y)
        self.sc.move_x_and_y(-self.tick_len, 0.0)
        self.sc.move_x_and_y(self.tick_len, 0.0)
        self.sc.move_x_and_y(0.0, self.mid_y)
        self.sc.move_x_and_y(-self.mid_x, 0.0)
        self.sc.move_x_and_y(0.0, -self.tick_len)
        self.sc.move_x_and_y(0.0, self.tick_len)
        self.sc.move_x_and_y(-self.mid_x, 0.0)
        self.sc.move_x_and_y(0.0, -self.mid_y)
        self.sc.move_x_and_y(self.tick_len, 0.0)
        self.sc.move_x_and_y(-self.tick_len, 0.0)
        self.sc.move_x_and_y(0.0, -self.mid_y)

    def walk_perimeter_to(self, x_pos, y_pos):
        # assume starting at origin

        if y_pos == 0.0:  # on the top face
            self.sc.move_x_and_y(x_pos, 0.0)
            return 0

        else:  # skip to right face
            self.sc.move_x_and_y(self.width, 0.0)

        if x_pos == self.width:  # on the right face
            self.sc.move_x_and_y(0.0, y_pos)
            return 1

        else:  # skip to the bottom face
            self.sc.move_x_and_y(0.0, self.height)

        if y_pos == self.height:  # on the bottom face
            self.sc.move_x_and_y(x_pos - self.width, 0.0)
            return 2

        else:  # skip to the left face
            self.sc.move_x_and_y(-self.width, 0.0)

        if x_pos == 0.0:  # on the left face
            self.sc.move_x_and_y(0.0, y_pos - self.height)
            return 3

        else:
            raise Exception("HEY! ({},{}) is not on the perimeter!".format(x_pos, y_pos))

    def draw_hands(self):
        clock_inner_r = self.mid_x
        t_hours = 4.0
        t_minutes = 45.0
        minute_sector, local_minute_angle = divmod(t_minutes, 15.0)
        local_minute_angle = (local_minute_angle / 15.0) * 90.0
        minute_perimeter_slice = clock_inner_r * math.tan(math.radians(local_minute_angle))
        # minute_perimeter_x1 = clock_inner_r * (2.0 - math.floor(minute_sector / 2.0))
        # minute_perimeter_y1 = clock_inner_r * (2.0 - math.floor(abs(minute_sector - 1.0) / 2.0))

        hour_sector = t_hours // 3.0
        local_hour_angle = (((t_hours + (t_minutes / 60.0)) % 3.0) / 3.0) * 90.0
        hour_perimeter_slice = clock_inner_r * math.tan(math.radians(90.0 - local_hour_angle))
        hour_perimeter_x1 = clock_inner_r * (2.0 - math.floor(hour_sector / 2.0))
        hour_perimeter_y1 = clock_inner_r * (2.0 - math.floor(abs(hour_sector - 1.0) / 2.0))

        if minute_sector == 0.0:  # 0 <= m < 15
            minute_perimeter_x1 = self.mid_x
            minute_perimeter_y1 = 0.0
            minute_perimeter_y2 = minute_perimeter_slice % self.mid_x
            minute_perimeter_x2 = minute_perimeter_slice - minute_perimeter_y2

        elif minute_sector == 1.0:  # 15 <= m < 30
            minute_perimeter_x1 = self.width
            minute_perimeter_y1 = self.mid_y
            minute_perimeter_y2 = minute_perimeter_slice % self.mid_x
            minute_perimeter_x2 = -(minute_perimeter_slice - minute_perimeter_y2)

        elif minute_sector == 2.0:  # 30 <= m < 45
            minute_perimeter_x1 = self.mid_x
            minute_perimeter_y1 = self.width
            minute_perimeter_y2 = -(minute_perimeter_slice % self.mid_x)
            minute_perimeter_x2 = -(minute_perimeter_slice + minute_perimeter_y2)

        else:  # 45 <= m < 60
            minute_perimeter_x1 = 0.0
            minute_perimeter_y1 = self.mid_y
            minute_perimeter_y2 = -(minute_perimeter_slice % self.mid_x)
            minute_perimeter_x2 = minute_perimeter_slice + minute_perimeter_y2

        minute_perimeter_xf = minute_perimeter_x1 + minute_perimeter_x2
        minute_perimeter_yf = minute_perimeter_y1 + minute_perimeter_y2



        print("minute_sector: {}".format(minute_sector))
        print("local_minute_angle: {}".format(local_minute_angle))
        print("minute_perimeter_slice: {}".format(minute_perimeter_slice))
        print("minute_perimeter_x1: {}".format(minute_perimeter_x1))
        print("minute_perimeter_y1: {}".format(minute_perimeter_y1))
        print("hour_sector: {}".format(hour_sector))
        print("local_hour_angle: {}".format(local_hour_angle))
        print("hour_perimeter_slice: {}".format(hour_perimeter_slice))
        print("hour_perimeter_x1: {}".format(hour_perimeter_x1))
        print("hour_perimeter_y1: {}".format(hour_perimeter_y1))

        self.walk_perimeter_to(minute_perimeter_xf, minute_perimeter_yf)

        x_to_center = self.mid_x - self.sc.x
        y_to_center = self.mid_y - self.sc.y

        self.sc.move_x_and_y(x_to_center, y_to_center)

        # TODO: Implement hours
        pass

    def refresh_clock(self):
        self.reset()
        self.paint_clockface()
        self.draw_hands()


def main():

    try:
        sc = SketchController()
        cs = ClockSketch(sc)
        # sc.move_x_and_y(5.3, 7.9, 0.1)
        # sc.move_x_and_y(2.1, 3.2, 0.2)
    except KeyboardInterrupt:
        print("\nKeyboardInterrupt catched.")
        print("Terminate main thread.")
        print("If only daemonic threads are left, terminate whole program.")
        exit(1)

if __name__ == '__main__':
    main()
