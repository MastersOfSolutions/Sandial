# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function
import threading
from time import sleep
import datetime
import codecs
from collections import deque
import math
from io import StringIO
import array

__author__ = 'ethan'

codecs.register(codecs.lookup)  # Fix LookupError thread race condition


class BetterStringIO(StringIO):
    def prewrite(self, *args, **kwargs):
        temp_cache = self.getvalue()
        self.seek(0)
        self.write(*args, **kwargs)
        self.write(temp_cache)

    def clear(self):
        self.seek(0)
        self.truncate()


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


class PiMotor(object):
    MOTOR_V = 3.0

    def __init__(self, gpio=None, pin_a=None, pin_b=None, pin_c=None):
        self.gpio = gpio
        self.pin_a = pin_a
        self.pin_b = pin_b
        self.pin_c = pin_c

    def register(self, io_controller, *pins):
        raise NotImplementedError

    def clockwise(self):
        raise NotImplementedError

    def counter_clockwise(self):
        raise NotImplementedError

    def start(self):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError

    def cleanup(self):
        raise NotImplementedError


class SketchController(object):
    DEFAULT_V = 3
    X_MOTOR_V = 3.0  # The velocity of the x motor
    Y_MOTOR_V = 3.0  # The velocity of the y motor

    def __init__(self):
        self.threads = deque()
        self._x_lock = threading.Lock()
        self._y_lock = threading.Lock()
        self.x_motor = PiMotor()
        self.y_motor = PiMotor()

        # TODO: self.x_motor.register(foo)
        # TODO: self.y_motor.register(foo)
        self.x = 0.0
        self.y = 0.0
        self.buddysync = BuddySync()

    def shake_to_clear(self):
        pass

    def return_to_origin(self):
        self.move_x_and_y(0.0 - self.x, 0.0 - self.y)

    def _move_x(self, delta_x):
        delta_t = abs(delta_x) / self.x_motor.MOTOR_V
        will_move = delta_x != 0.0

        # init the direction
        if delta_x < 0:
            self.x_motor.counter_clockwise()
        elif delta_x > 0:
            self.x_motor.clockwise()

        self.buddysync.buddy_up()
        if will_move:
            self.x_motor.start()
            sleep(delta_t)
            self.x_motor.stop()
            self.x += delta_x

    def _move_y(self, delta_y):
        delta_t = abs(delta_y) / self.y_motor.MOTOR_V
        will_move = delta_y != 0.0

        # init the direction
        if delta_y < 0:
            self.y_motor.counter_clockwise()
        elif delta_y > 0:
            self.y_motor.clockwise()

        self.buddysync.buddy_up()
        if will_move:
            self.y_motor.start()
            sleep(delta_t)
            self.y_motor.stop()
            self.y += delta_y

    def move_x_and_y(self, delta_x, delta_y):
        old_x, old_y = self.x, self.y

        with self._x_lock:
            with self._y_lock:
                # Kudos to http://stackoverflow.com/a/12376400/4437749
                t1 = threading.Thread(target=self._move_x, args=(delta_x,))
                t2 = threading.Thread(target=self._move_y, args=(delta_y,))
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


class SVGSketchController(object):
    DEFAULT_V = 3

    def __init__(self):
        self.threads = deque()
        self._x_lock = threading.Lock()
        self._y_lock = threading.Lock()
        self.x_deltas = deque()
        self.y_deltas = deque()
        self.x_coords = deque()
        self.y_coords = deque()
        self.x = 0.0
        self.y = 0.0
        self.x_coords.append(self.x)
        self.y_coords.append(self.y)
        self.x_deltas.append(0.0)
        self.y_deltas.append(0.0)
        self.heartbeat = HeartbeatSync()
        self.buddysync = BuddySync()
        self.x_move_ts = None
        self.y_move_ts = None
        self.svg_file = StringIO()
        self.path_d_val_buffer = StringIO()
        self.anim_d_val_buffer = StringIO()
        self.anim_cx_val_buffer = StringIO()
        self.anim_cy_val_buffer = StringIO()
        self.buffers = (self.svg_file, self.path_d_val_buffer, self.anim_d_val_buffer, self.anim_cx_val_buffer,
                        self.anim_cy_val_buffer)
        self.svg_width = self.svg_height = self.svg_margin = -1.0

    @property
    def svg_header(self):
        return "<svg width=\"100%\" height=\"100%\" viewBox=\"0 0 {} {}\" xmlns=\"http://www.w3.org/2000/svg\">" \
               "\n".format(int(self.svg_width + (2 * self.svg_margin)), int(self.svg_height + (2 * self.svg_margin)))

    def build_svg(self, make_animated=True):
        self.svg_file.write(self.svg_header)
        self.svg_file.write("<g transform=\"translate({0} {0})\">\n".format(self.svg_margin))

        # Freeze the deque to a uniform array for that fast address-math access
        x_deltas_frozen = array.array('f', self.x_deltas)
        y_deltas_frozen = array.array('f', self.y_deltas)
        x_coords_frozen = array.array('f', self.x_coords)
        y_coords_frozen = array.array('f', self.y_coords)

        deltas_len = len(x_deltas_frozen)
        for delta_i in xrange(0, deltas_len):
            x_delta_i = x_deltas_frozen[delta_i]
            y_delta_i = y_deltas_frozen[delta_i]
            if x_delta_i == 0.0 and y_delta_i == 0.0:
                segment_str = "M0 0"
            elif x_delta_i == 0.0:
                y_delta_i = int(y_delta_i) if y_delta_i % 1.0 == 0.0 else y_delta_i
                segment_str = "v{}".format(y_delta_i)
            elif y_delta_i == 0.0:
                x_delta_i = int(x_delta_i) if x_delta_i % 1.0 == 0.0 else x_delta_i
                segment_str = "h{}".format(x_delta_i)
            else:
                x_delta_i = int(x_delta_i) if x_delta_i % 1.0 == 0.0 else x_delta_i
                y_delta_i = int(y_delta_i) if y_delta_i % 1.0 == 0.0 else y_delta_i
                segment_str = "l{} {}".format(x_delta_i, y_delta_i)

            self.path_d_val_buffer.write(segment_str)
            if make_animated:
                if not (x_delta_i == 0.0 and y_delta_i == 0.0 and delta_i == 0):
                    self.anim_d_val_buffer.write(";{}".format(self.path_d_val_buffer.getvalue()))

        if make_animated:
            anim_path2 = StringIO()
            anim_path2.write("M0 0l8 0")
            coords_len = len(x_coords_frozen)
            for coords_i in xrange(0, coords_len):
                x_coord_i = x_coords_frozen[coords_i]
                y_coord_i = y_coords_frozen[coords_i]
                x_coord_i = int(x_coord_i) if x_coord_i % 1.0 == 0.0 else x_coord_i
                y_coord_i = int(y_coord_i) if y_coord_i % 1.0 == 0.0 else y_coord_i
                self.anim_cx_val_buffer.write(";{}".format(x_coord_i))
                self.anim_cy_val_buffer.write(";{}".format(y_coord_i))
                anim_path2.write(";M{} {}l8 0".format(x_coord_i, y_coord_i))
            full_anim_cx = self.anim_cx_val_buffer.getvalue()
            self.anim_cx_val_buffer.seek(0)
            self.anim_cx_val_buffer.write("{}".format(self.x_coords[-1]))
            self.anim_cx_val_buffer.write(full_anim_cx)

            full_anim_cy = self.anim_cy_val_buffer.getvalue()
            self.anim_cy_val_buffer.seek(0)
            self.anim_cy_val_buffer.write("{}".format(self.y_coords[-1]))
            self.anim_cy_val_buffer.write(full_anim_cy)

            full_anim_d = self.anim_d_val_buffer.getvalue()
            self.anim_d_val_buffer.seek(0)
            self.anim_d_val_buffer.write(self.path_d_val_buffer.getvalue())
            self.anim_d_val_buffer.write(full_anim_d)

            elem_c_buf = StringIO()
            elem_c_buf.write("<circle cx=\"0\" cy=\"0\" r=\"8\">\n "
                             "<animate attributeName=\"cx\" attributeType=\"XML\" dur=\"10s\" "
                             "repeatCount=\"indefinite\"\n values=\"")
            elem_c_buf.write(self.anim_cx_val_buffer.getvalue())
            elem_c_buf.write("\"/>\n <animate attributeName=\"cy\" attributeType=\"XML\" dur=\"10s\" "
                             "repeatCount=\"indefinite\"\n values=\"")
            elem_c_buf.write(self.anim_cy_val_buffer.getvalue())
            elem_c_buf.write("\"/>\n</circle>\n")

            self.svg_file.write("<path id=\"p1\" stroke=\"black\" stroke-width=\"3\" fill=\"transparent\" d=\"")
            self.svg_file.write(self.path_d_val_buffer.getvalue())
            self.svg_file.write("\">\n<animate attributeName=\"d\" attributeType=\"XML\" dur=\"10s\" "
                                "repeatCount=\"1\"\nvalues=\"")
            self.svg_file.write(self.anim_d_val_buffer.getvalue())
            #  self.svg_file.write("\"/>\n<use href=\"#anim1\"/></path>\n")
            self.svg_file.write("\"/>\n</path>\n")

            #elem_c_buf.write("<circle cx=\"\" cy=\"\" r=\"8\">\n"
            #                 "<animateMotion dur=\"10s\" repeat=\"indefinite\">\n"
            #                 "<mpath href=\"#p1\"/>\n</animateMotion>\n</circle>\n")
            self.svg_file.write(elem_c_buf.getvalue())
            elem_c_buf.close()

        else:  # if not make_animated
            self.svg_file.write("<path stroke=\"black\" stroke-width=\"3\" fill=\"transparent\" d=\"")
            self.svg_file.write(self.path_d_val_buffer.getvalue())
            self.svg_file.write("\"/>")

        self.svg_file.write("</g>\n</svg>\n")

    def init_svg(self, width=600.0, height=600.0, margin=50.0):
        self.svg_width = width
        self.svg_height = height
        self.svg_margin = margin
        self.x_coords.append(0.0)
        self.y_coords.append(0.0)
        self.x_deltas.append(0.0)
        self.y_deltas.append(0.0)

    def shake_to_clear(self):
        for buf in self.buffers:
            buf.seek(0)
            buf.truncate()
        self.x_deltas.clear()
        self.y_deltas.clear()
        self.x_coords.clear()
        self.y_coords.clear()
        self.init_svg(width=self.svg_width, height=self.svg_height, margin=self.svg_margin)

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
        self.buddysync.buddy_up()
        move_ts = datetime.datetime.now()
        self.x_move_ts = move_ts

        sleep(t)
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
        # print("starting _move_y {}\n".format(move_ts))
        sleep(t)
        # print("done _move_y {}\n".format(datetime.datetime.now()))
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

    def move_x_and_y(self, delta_x, delta_y, delta_t=0.00002):
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
        self.x_deltas.append(delta_x)
        self.y_deltas.append(delta_y)
        self.x_coords.append(self.x)
        self.y_coords.append(self.y)

        print("({},{}) --> ({},{})\n".format(old_x, old_y, self.x, self.y))

    def wait_in_line(self):
        for t in self.threads:
            while t.isAlive():
                t.join(5)
        self.threads.clear()

    def export_svg(self, as_animated=True):
        self.build_svg(make_animated=as_animated)
        return self.svg_file.getvalue()


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
        self.height = self.width = 600.0
        self.tick_len = 40.0
        self.mid_y = self.mid_x = self.width / 2.0
        assert isinstance(sketch_controller, SVGSketchController)
        self.sc = sketch_controller
        assert isinstance(self.sc, SVGSketchController)
        self.sc.init_svg(width=self.width, height=self.height, margin=50.0)
        self.refresh_clock()

    def reset(self):
        delta_x_orig = self.origin_x - self.sc.x
        delta_y_orig = self.origin_y - self.sc.y
        self.sc.move_x_and_y(delta_x_orig, delta_y_orig)
        self.sc.shake_to_clear()

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

    def draw_hands(self, t_hours=3.0, t_minutes=0.1):
        clock_inner_r = self.mid_x
        t_am_pm, t_hours_float = divmod(t_hours + (t_minutes / 60.0), 12.0)

        minute_sector = t_minutes // 15.0
        # local_minute_angle = (local_minute_angle / 15.0) * 90.0
        local_minute_angle = (t_minutes % 15.0) * 6.0
        local_minute_angle_rad = math.radians(local_minute_angle)
        minute_perimeter_slice = clock_inner_r * math.tan(local_minute_angle_rad)
        minute_inner_adj = self.mid_x

        if local_minute_angle == 0.0:
            minute_inner_opp1 = 0.0
            minute_inner_opp2 = 0.0
        elif local_minute_angle == 45.0:
            minute_inner_opp1 = self.mid_x
            minute_inner_opp2 = 0.0

        elif local_minute_angle == 90.0:
            minute_inner_opp1 = self.mid_x
            minute_inner_opp2 = self.mid_x

        elif 0.0 < local_minute_angle < 45.0:
            minute_inner_opp1 = self.mid_x * math.tan(local_minute_angle_rad)
            minute_inner_opp2 = 0.0

        elif 45.0 < local_minute_angle < 90.0:
            minute_inner_opp1 = self.mid_x
            minute_inner_opp2 = self.mid_x * math.tan(math.radians(local_minute_angle % 45.0))
        else:
            raise Exception("HEY! {}degrees is not a valid local minute angle!".format(local_minute_angle))

        hour_sector = t_hours_float // 3.0
        # local_hour_angle = (((t_hours + (t_minutes / 60.0)) % 3.0) / 3.0) * 90.0
        local_hour_angle = (t_hours_float % 3.0) * 30.0
        local_hour_angle_rad = math.radians(local_hour_angle)

        hour_perimeter_slice = clock_inner_r * math.tan(math.radians(local_hour_angle))
        hour_inner_radius = self.mid_x / 2.0
        hour_inner_slice_opp = hour_inner_radius * math.sin(local_hour_angle_rad)
        hour_inner_slice_adj = hour_inner_radius * math.cos(local_hour_angle_rad)

        if minute_sector == 0.0:  # 0 <= m < 15
            minute_perimeter_x1 = self.mid_x
            minute_perimeter_y1 = 0.0
            minute_perimeter_x2 = minute_inner_opp1
            minute_perimeter_y2 = minute_inner_opp2

        elif minute_sector == 1.0:  # 15 <= m < 30
            minute_perimeter_x1 = self.width
            minute_perimeter_y1 = self.mid_y
            minute_perimeter_x2 = -minute_inner_opp2
            minute_perimeter_y2 = minute_inner_opp1

        elif minute_sector == 2.0:  # 30 <= m < 45
            minute_perimeter_x1 = self.mid_x
            minute_perimeter_y1 = self.width
            minute_perimeter_x2 = -minute_inner_opp1
            minute_perimeter_y2 = -minute_inner_opp2

        else:  # 45 <= m < 60
            minute_perimeter_x1 = 0.0
            minute_perimeter_y1 = self.mid_y
            minute_perimeter_x2 = minute_inner_opp2
            minute_perimeter_y2 = -minute_inner_opp1

        minute_perimeter_xf = minute_perimeter_x1 + minute_perimeter_x2
        minute_perimeter_yf = minute_perimeter_y1 + minute_perimeter_y2

        if hour_sector == 0.0 or t_hours == 0.0:  # 0 <= m < 3
            hour_inner_xf = hour_inner_slice_opp
            hour_inner_yf = -hour_inner_slice_adj

        elif hour_sector == 1.0:  # 3 <= m < 6
            hour_inner_xf = hour_inner_slice_adj
            hour_inner_yf = hour_inner_slice_opp

        elif hour_sector == 2.0:  # 6 <= m < 9
            hour_inner_xf = -hour_inner_slice_opp
            hour_inner_yf = hour_inner_slice_adj

        else:  # 9 <= m < 12
            hour_inner_xf = -hour_inner_slice_adj
            hour_inner_yf = -hour_inner_slice_opp

        print("t_minutes: {}".format(t_minutes))
        print("t_hours: {}".format(t_hours))
        print("minute_sector: {}".format(minute_sector))
        print("local_minute_angle: {}".format(local_minute_angle))
        print("minute_perimeter_slice: {}".format(minute_perimeter_slice))
        print("minute_perimeter_x1: {}".format(minute_perimeter_x1))
        print("minute_perimeter_y1: {}".format(minute_perimeter_y1))
        print("minute_perimeter_x2: {}".format(minute_perimeter_x2))
        print("minute_perimeter_y2: {}".format(minute_perimeter_y2))
        print("minute_perimeter_xf: {}".format(minute_perimeter_xf))
        print("minute_perimeter_yf: {}".format(minute_perimeter_yf))
        print("hour_sector: {}".format(hour_sector))
        print("local_hour_angle: {}".format(local_hour_angle))
        print("hour_perimeter_slice: {}".format(hour_perimeter_slice))
        print("hour_inner_xf: {}".format(hour_inner_xf))
        print("hour_inner_yf: {}".format(hour_inner_yf))

        self.walk_perimeter_to(minute_perimeter_xf, minute_perimeter_yf)

        x_to_center = self.mid_x - self.sc.x
        y_to_center = self.mid_y - self.sc.y

        self.sc.move_x_and_y(x_to_center, y_to_center)
        self.draw_am_or_pm(t_am_or_pm=t_am_pm)
        self.sc.move_x_and_y(hour_inner_xf, hour_inner_yf)

    def draw_am_or_pm(self, t_am_or_pm):
        assert t_am_or_pm in (0, 1)
        up_or_down = -1.0 if t_am_or_pm == 0 else 1.0

        self.sc.move_x_and_y(-self.tick_len, 0.0)
        self.sc.move_x_and_y(0.0, up_or_down * self.tick_len)
        self.sc.move_x_and_y(self.tick_len * 2.0, 0.0)
        self.sc.move_x_and_y(0.0, up_or_down * -self.tick_len)
        self.sc.move_x_and_y(-self.tick_len, 0.0)

    def refresh_clock(self, t_hours=3.0, t_minutes=0.1, animated=True):
        self.reset()
        self.paint_clockface()
        self.draw_hands(t_hours=t_hours, t_minutes=t_minutes)
        return self.sc.export_svg(as_animated=animated)


def main():

    try:
        sc = SVGSketchController()
        cs = ClockSketch(sc)
        for h1 in xrange(20, 24):
            h1 = float(h1)
            for m1 in xrange(0, 60, 1):
                m1 = float(m1)
                svg1 = cs.refresh_clock(h1, m1, True)
                with open("clocks/clock_{:0>2.0f}_{:0>2.0f}.svg".format(h1, m1), "w") as fd1:
                    fd1.write(str(svg1))
        # sc.move_x_and_y(5.3, 7.9, 0.1)
        # sc.move_x_and_y(2.1, 3.2, 0.2)
    except KeyboardInterrupt:
        print("\nKeyboardInterrupt catched.")
        print("Terminate main thread.")
        print("If only daemonic threads are left, terminate whole program.")
        exit(1)

if __name__ == '__main__':
    main()
