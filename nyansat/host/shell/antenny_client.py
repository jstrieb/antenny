# Client middle layer
import ast
import asyncio
import json
import logging
import threading

from time import sleep
from dataclasses import dataclass
from typing import List

from nyansat.host.shell.terminal_printer import TerminalPrinter
from nyansat.host.shell.command_invoker import CommandInvoker
from nyansat.host.shell.nyan_explorer import NyanExplorer
from nyansat.host.shell.errors import *

from mp.pyboard import PyboardError
from mp.mpfexp import MpFileExplorer
from nyansat.host.shell.nyan_pyboard import NyanPyboard

from nyansat.host.satellite_observer import SatelliteObserver, parse_tle_file


import nyansat.host.satdata_client as SatelliteScraper


# TODO: Move error messages into the errors.py as a self.message attribute
def exception_handler(func):

    def wrapper(*args, **kwargs):
        try:
            func(*args, **kwargs)
        except NotRespondingError as e:
            logging.error(e)
            print("The AntKontrol object is not responding. Restart it with 'antkontrol start'")
        except NoAntKontrolError as e:
            print("Please run 'antkontrol start' to initialize the antenna.")
            logging.error(e)
        except DeviceNotOpenError as e:
            print("Not connected to device. Use 'open' first.")
            logging.error(e)
        except AntKontrolInitError as e:
            logging.error(e)
            print("Error creating AntKontrol object. Please check your physical setup and configuration match up")
        except SafeModeWarning as e:
            logging.warning(e)
            print("AntKontrol is in SAFE MODE. Attached motors will not move")
            print("If you did not intend to be in SAFE MODE, check your configuration and run "
                  "'antkontrol start'")
        except NotVisibleError:
            print("The satellite is not visible from your position")
        except BNO055RegistersError as e:
            logging.error(e)
            print("Error: BNO055 not detected or error in writing calibration registers.")
        except BNO055UploadError as e:
            logging.error(e)
            print("The AntKontrol object is either not responding or your current configuration does not support IMU "
                  "calibration.")
            print("You can try to restart AntKontrol by running 'antkontrol start'")
            print("If you believe your configuration is incorrect, run 'configs' to check your configuration and "
                  "'setup <CONFIG_FILE>' to create a new one\n")
        except PinInputError as e:
            logging.error(e)
            print("Invalid type for pin number. Try again using only decimal numbers")
        except I2CNoAddressesError as e:
            logging.error(e)
            print("Did not find any I2C devices")
        except ConfigStatusError as e:
            logging.error(e)
            print("Could not access existing configuration object or create one.")
        except NoSuchConfigError as e:
            logging.error(e)
            print("No such configuration parameter.")
        except ConfigUnknownError as e:
            logging.error(e)
            print("Command faulted while trying to set configuration.")
        except ValueError as e:
            logging.error(e)
            print("Incorrect parameter type.")
        except NoSuchFileError as e:
            logging.error(e)
            print("No such file")
        except NotTrackingError as e:
            logging.error(e)
            print("The antenna is not currently tracking any satellite")

    return wrapper


class AntennyClient(object):

    def __init__(self, fe: MpFileExplorer):
        self.fe = fe
        self.invoker = CommandInvoker(fe.con)
        self.tracking = None
        self.prompts = {
            "gps_uart_tx": ("GPS UART TX pin#: ", int),
            "gps_uart_rx": ("GPS UART RX pin#: ", int),
            "use_gps": ("Use GPS (true or false): ", bool),
            "i2c_servo_scl": ("Servo SCL pin#: ", int),
            "i2c_servo_sda": ("Servo SDA pin#: ", int),
            "i2c_servo_address": ("Servo address (in decimal): ", int),
            "i2c_bno_scl": ("BNO055 SCL pin#: ", int),
            "i2c_bno_sda": ("BNO055 SDA pin#: ", int),
            "i2c_bno_address": ("BNO055 address (in decimal): ", int),
            "use_imu": ("Use IMU (true or false): ", bool),
            "i2c_screen_scl": ("Screen SCL pin#: ", int),
            "i2c_screen_sda": ("Screen SDA pin#: ", int),
            "i2c_screen_address": ("Screen address (in decimal): ", int),
            "use_screen": ("Use Screen (true or false): ", bool),
            "elevation_servo_index": ("Servo default elevation index: ", float),
            "azimuth_servo_index": ("Servo default azimuth index: ", float),
            "elevation_max_rate": ("Servo elevation max rate: ", float),
            "azimuth_max_rate": ("Servo azimuth max rate: ", float),
            "use_webrepl": ("Use WebREPL: ", bool),
            "use_telemetry": ("Use Telemetry: ", bool)
        }

    def safemode_guard(self):
        """Warns user if AntKontrol is in SAFE MODE while using motor-class commands"""
        if self.invoker.is_safemode():
            raise SafeModeWarning

    def guard_open(self):
        if self.fe or self.invoker is None:
            raise DeviceNotOpenError
        else:
            return True

    def guard_init(self):
        if not self.invoker.is_antenna_initialized():
            raise NoAntKontrolError
        else:
            return True

    def guard_config_status(self):
        if not self.invoker.config_status():
            raise ConfigStatusError
        else:
            return True

    @exception_handler
    def elevation(self, el):
        self.guard_open()
        self.guard_init()
        self.safemode_guard()
        self.invoker.set_elevation_degree(el)

    @exception_handler
    def azimuth(self, az):
        self.guard_open()
        self.guard_init()
        self.safemode_guard()
        self.invoker.set_elevation_degree(az)

    @exception_handler
    def antkontrol(self, mode):
        self.guard_open()
        if mode == 'start':
            if self.invoker.is_antenna_initialized():
                self.invoker.delete_antkontrol()

            # TODO: raise BNO055UploadError in nyan_explorer
            ret = self.invoker.create_antkontrol()
            self.safemode_guard()
            if self.invoker.is_antenna_initialized():
                print("AntKontrol initialized")
            else:
                raise AntKontrolInitError
        elif mode == 'status':
            self.guard_init()
            if self.invoker.is_safemode():
                print("AntKontrol is running in SAFE MODE")
            else:
                print("AntKontrol appears to be initialized properly")

    @exception_handler
    def track(self, sat_name):
        self.guard_open()
        self.guard_init()
        # TODO: raise NotVisibleError
        self.wrap_track(sat_name)
        pass

    @exception_handler
    def cancel(self):
        # TODO: Same as for track
        self.guard_open()
        self.guard_init()
        if self.invoker.is_tracking():
            self.invoker.cancel()
        else:
            raise NotTrackingError

    @exception_handler
    def upload_calibration(self):
        self.guard_open()
        self.guard_init()

        # TODO: raise BNO055UploadError in nyan_explorer
        status = self.invoker.imu_upload_calibration_profile()
        if not status:
            raise BNO055RegistersError

    @exception_handler
    def save_calibration(self):
        self.guard_open()
        self.guard_init()

        # TODO: raise BNO055UploadError in nyan_explorer
        status = self.invoker.imu_save_calibration_profile()
        if not status:
            raise BNO055RegistersError

    # TODO: This one is huge, needs to be broken up
    @exception_handler
    def calibrate(self):
        pass

    @exception_handler
    def i2ctest(self):
        print("Input the SDA pin and SCL for the I2C bus to check")

        try:
            sda = int(input("SDA Pin#: "))
            scl = int(input("SCL Pin#: "))
        except ValueError:
            raise PinInputError

        # TODO: raise appropriate error in nyan_explorer
        addresses = self.invoker.i2c_scan(sda, scl)
        addresses_list = addresses.strip('] [').strip(', ')
        if not addresses_list:
            raise I2CNoAddressesError
        else:
            print("Found the following device addresses: {}".format(addresses_list))
        print("If you had a running AntKontrol instance, be sure to restart it")

    @exception_handler
    def motor_test(self, motor, pos):
        self.guard_open()
        self.guard_init()
        self.safemode_guard()
        if motor == 'EL':
            index = self.invoker.config_get(self.invoker.EL_SERVO_INDEX)
        elif motor == "AZ":
            index = self.invoker.config_get(self.invoker.AZ_SERVO_INDEX)
        else:
            # Shouldn't happen
            raise ValueError
        data = self.invoker.motor_test(index, pos)
        real_pos, x_angle, y_angle, z_angle = data

        print("real imu angles: %d", real_pos)
        print("expected position: %d", real_pos)

    @exception_handler
    def setup(self, name):
        self.guard_open()
        current = self.invoker.which_config()
        print("Welcome to Antenny!")
        print("Please enter the following information about your hardware\n")

        for k, info in self.prompts.items():
            prompt_text, typ = info
            try:
                new_val = typ(input(prompt_text))
            except ValueError:
                new_val = self.invoker.config_get_default(k)
                print("Invalid type, setting to default value \"{}\".\nUse \"set\" to "
                      "change the parameter".format(new_val))

            self.invoker.config_set(k, new_val)

        # TODO: figure this out, do we need this (make caching by default?)
        # if self.caching:
            # self.fe.cache = {}

        print("\nConfiguration set for \"{}\"!\n".format(name) +
              "You can use \"set\" to change individual parameters\n"
              "or \"edit\" to change the config file "
              "directly")

    @exception_handler
    def set(self, key, new_val):
        self.guard_open()

        # TODO: raise appropriate NoSuchConfig error in nyan_explorer
        old_val = self.invoker.config_get(key)
        _, typ = self.prompts[key]
        new_val = typ(new_val)

        self.invoker.config_set(key, new_val)
        print("Changed " + "\"" + key + "\" from " + str(old_val) + " --> " + str(new_val))

    @exception_handler
    def configs(self):
        # TODO: Something with ConfigUnknownError
        self.guard_open()
        print("-Config parameters-\n" +
              "Using \"{}\"".format(self.invoker.which_config()))
        for key in self.prompts.keys():
            print(key + ": " + self.invoker.config_get(key))

    @exception_handler
    def switch(self, name):
        self.guard_open()
        self.guard_config_status()

        files = self.fe.ls()
        if name not in files:
            raise NoSuchFileError
        current = self.invoker.which_config()
        self.invoker.config_switch(name)
        print("Switched from \"{}\"".format(current) +
              " to \"{}\"".format(name))

    def is_tracking(self):
        return self.tracking

    def _track_update(self, observer):
        """Update the antenna position every 2 seconds"""
        print(f"Tracking {observer.sat_name} ...")
        while self.tracking:
            elevation, azimuth, distance = observer.get_current_stats()
            self.invoker.set_elevation_degree(elevation)
            self.invoker.set_azimuth_degree(azimuth)
            sleep(2)

    async def _start_track(self, sat_name):
        """Track a satellite across the sky"""
        coords = (40.0, -73.0)
        tle_data_encoded = await SatelliteScraper.load_tle()
        tle_data = parse_tle_file(tle_data_encoded)
        observer = SatelliteObserver.parse_tle(coords, sat_name, tle_data)

        if not observer.get_visible():
            self.cancel()
            raise NotVisibleError
        t = threading.Thread(target=self._track_update, args=(observer,))
        t.start()

    def _wrap_track(self, sat_name):
        """Entry point for tracking mode"""
        self.tracking = True
        asyncio.run(self._start_track(sat_name))

    def _cancel(self):
        """Cancel tracking mode"""
        self.tracking = False

    # TODO: refactor this
    def bno_test(self, sda, scl):
        """
        Create a BNO controller object for the given I2C sda/scl configuration. Uses the default
        value of 40 for the BNO055 I2C address.
        :param sda: Pin number for sda
        :param scl: Pin number for scl
        :return: A BnoTestDiagnostics object containing relevant T/F information about the setup
        """
        i2c_bus_scannable = False
        i2c_addresses = []
        bno_object_created = False
        bno_object_calibrated = False

        # Test scanning I2C bus
        try:
            addresses = self.i2c_scan(sda, scl)
        except PyboardError:
            return BnoTestDiagnostics(
                i2c_bus_scannable,
                i2c_addresses,
                bno_object_created,
                bno_object_calibrated
            )
        i2c_bus_scannable = True

        # Test what's on the I2C bus and their addresses
        try:
            i2c_addresses = [int(n) for n in addresses.strip('] [').split(', ')]
            if not i2c_addresses:
                return BnoTestDiagnostics(
                    i2c_bus_scannable,
                    i2c_addresses,
                    bno_object_created,
                    bno_object_calibrated
                )
        except ValueError:
            return BnoTestDiagnostics(
                i2c_bus_scannable,
                i2c_addresses,
                bno_object_created,
                bno_object_calibrated
            )

        # Test creating BNO object
        try:
            self.exec_("from imu.imu_bno055 import Bno055ImuController")
            self.exec_("bno = Bno055ImuController(i2c)")
        except PyboardError:
            return BnoTestDiagnostics(
                i2c_bus_scannable,
                i2c_addresses,
                bno_object_created,
                bno_object_calibrated
            )
        bno_object_created = True

        # Test calibration status of BNO object
        try:
            calibration_status = json.loads(self.eval_string_expr("bno.get_calibration_status()"))
            bno_object_calibrated = calibration_status['system'] > 0
        except PyboardError:
            bno_object_calibrated = False

        return BnoTestDiagnostics(
            i2c_bus_scannable,
            i2c_addresses,
            bno_object_created,
            bno_object_calibrated
        )

    # TODO: refactor this
    def pwm_test(self, sda, scl):
        """
        Create a PCA9685 controller object for the given I2C sda/scl configuration. Uses the default
        value of 40 for the controller's address.
        :param sda: Pin number for sda
        :param scl: Pin number for scl
        :return: A PwmTestDiagnostics object containing relevant T/F information about the setup
        """
        i2c_bus_scannable = False
        i2c_addresses = []
        pca_object_created = False

        # Test scanning I2C bus
        try:
            addresses = self.i2c_scan(sda, scl)
        except PyboardError:
            return PwmTestDiagnostics(
                i2c_bus_scannable,
                i2c_addresses,
                pca_object_created
            )
        i2c_bus_scannable = True

        # Test what's on the I2C bus and their addresses
        try:
            i2c_addresses = [int(n) for n in addresses.strip('] [').split(', ')]
            if not i2c_addresses:
                return PwmTestDiagnostics(
                    i2c_bus_scannable,
                    i2c_addresses,
                    pca_object_created
                )
        except ValueError:
            return PwmTestDiagnostics(
                i2c_bus_scannable,
                i2c_addresses,
                pca_object_created
            )

        # Test creating BNO object
        try:
            self.exec_("from motor.motor_pca9685 import Pca9685Controller")
            self.exec_("pca = Pca9685Controller(i2c)")
            pca_object_created = True
        except PyboardError:
            pca_object_created = False

        return PwmTestDiagnostics(
            i2c_bus_scannable,
            i2c_addresses,
            pca_object_created
        )


@dataclass
class BnoTestDiagnostics:
    """Store diagnostic T/F values for BNO test. Used in the handling for 'bnotest' command."""
    i2c_bus_scannable: bool
    i2c_addresses: List[int]
    bno_object_created: bool
    bno_object_calibrated: bool

@dataclass
class PwmTestDiagnostics:
    """Store diagnostic T/F values for PWM test. Used in the handling for 'pwmtest' command."""
    i2c_bus_scannable: bool
    i2c_addresses: List[int]
    pca_object_created: bool