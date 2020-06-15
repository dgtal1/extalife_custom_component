""" ExtaLife JSON API wrapper library. Enables device control, discovery and status fetching from EFC-01 controller """
from __future__ import print_function

import logging
import socket
import json
import threading

log = logging.getLogger(__name__)

# device type (channel_data.data.type)
DEVICE_ARR_SENS_TEMP = [2, 4, 20, 21]
DEVICE_ARR_SENS_LIGHT = []
DEVICE_ARR_SENS_HUMID = []
DEVICE_ARR_SENS_MULTI = [28]
DEVICE_ARR_SENS_WATER = [42]
DEVICE_ARR_SENS_MOTION = [41]
DEVICE_ARR_SWITCH = [10, 11, 22, 23, 24, 80]
DEVICE_ARR_COVER = [12, 25]
DEVICE_ARR_LIGHT = [13, 26, 45, 27, 46]
DEVICE_ARR_LIGHT_RGB = []     #RGB only
DEVICE_ARR_LIGHT_RGBW = [27, 38]
DEVICE_ARR_LIGHT_EFFECT = [27, 38]
DEVICE_ARR_CLIMATE = [16]
DEVICE_ARR_REPEATER = [237]

DEVICE_ARR_ALL_SWITCH = DEVICE_ARR_SWITCH
DEVICE_ARR_ALL_LIGHT = [*DEVICE_ARR_LIGHT, *DEVICE_ARR_LIGHT_RGB, *DEVICE_ARR_LIGHT_RGBW]
DEVICE_ARR_ALL_COVER = [*DEVICE_ARR_COVER]
DEVICE_ARR_ALL_CLIMATE = [*DEVICE_ARR_CLIMATE]
DEVICE_ARR_ALL_IGNORE = [*DEVICE_ARR_REPEATER]

# measurable magnitude/quantity:
DEVICE_ARR_ALL_SENSOR_MEAS = [
    *DEVICE_ARR_SENS_TEMP,
    *DEVICE_ARR_SENS_HUMID,
]
# binary sensors:
DEVICE_ARR_ALL_SENSOR_BINARY = [
    *DEVICE_ARR_SENS_WATER,
    *DEVICE_ARR_SENS_MOTION,
]
DEVICE_ARR_ALL_SENSOR_MULTI = [*DEVICE_ARR_SENS_MULTI]
DEVICE_ARR_ALL_SENSOR = [
    *DEVICE_ARR_ALL_SENSOR_MEAS,
    *DEVICE_ARR_ALL_SENSOR_BINARY,
    *DEVICE_ARR_ALL_SENSOR_MULTI,
]

DEVICE_ICON_ARR_LIGHT = [
    15,
    13,
    8,9,14,16,17,
]  # override device and type rules based on icon; force 'light' MQTT device for some icons, but only when device was detected preliminarly as switch; 28 =LED


class ExtaLifeAPI:
    """ Main API class: wrapper for communication with controller """

    # Commands
    CMD_LOGIN = 1
    CMD_CONTROL_DEVICE = 20
    CMD_FETCH_RECEIVERS = 37
    CMD_FETCH_EXTAFREE = 203
    CMD_FETCH_SENSORS = 38
    CMD_VERSION = 151
    CMD_RESTART = 150

    # Actions
    ACTN_TURN_ON = "TURN_ON"
    ACTN_TURN_OFF = "TURN_OFF"
    ACTN_SET_BRI = "SET_BRIGHTNESS"
    ACTN_SET_RGB = "SET_COLOR"
    ACTN_SET_POS = "SET_POSITION"
    ACTN_SET_TMP = "SET_TEMPERATURE"
    ACTN_STOP = "STOP"
    ACTN_OPEN = "UP"
    ACTN_CLOSE = "DOWN"
    ACTN_SET_SLR_MODE = "SET_MODE"
    ACTN_SET_RGT_MODE_MANUAL = "RGT_SET_MODE_MANUAL"
    ACTN_SET_RGT_MODE_AUTO = "RGT_SET_MODE_AUTO"
    ACTN_EXFREE_TURN_ON_PRESS = "TURN_ON_PRESS"
    ACTN_EXFREE_TURN_ON_RELEASE = "TURN_ON_RELEASE"
    ACTN_EXFREE_TURN_OFF_PRESS = "TURN_OFF_PRESS"
    ACTN_EXFREE_TURN_OFF_RELEASE = "TURN_OFF_RELEASE"

    def __init__(self, user, password, **kwargs):
        self.host = kwargs.get("host")
        self.user = user
        self.password = password

        # perform controller autodiscovery if no IP specified
        if self.host is None:
            self.host = TCPAdapter.discover_controller()

        # check if still None after autodiscovery
        if not self.host:
            raise TCPConnError("Could not find controller IP via autodiscovery")

        # init TCP adapter and try to connect
        self.tcp = TCPAdapter(user, password)

        # connect and login - may raise TCPConnErr
        log.debug("Connecting to controller using IP: %s", self.host)
        resp = self.tcp.connect(self.host)

        # check response if login succeeded
        if resp[0]["status"] != "success":
            raise TCPConnError(resp)

    @classmethod
    def discover_controller(cls):
        """ Returns controller IP address if found, otherwise None"""
        return TCPAdapter.discover_controller()

    def get_version_info(self):
        """ Get controller software version """
        cmd_data = {"data": None}
        try:
            resp = self.tcp.exec_command(self.CMD_VERSION, cmd_data)
            return resp[0]["data"]["new_version"]

        except TCPCmdError:
            log.error("Command %s could not be executed", self.CMD_VERSION)
            return

    def get_channels(self, include=None, func=None):
        """
        Get list of dicts of Exta Life channels consisting of native Exta Life TCP JSON
        data, but with transformed data model. Each channel will have native channel info
        AND device info. 2 channels of the same device will habe the same device attributes
        """
        try:
            cmd = self.CMD_FETCH_RECEIVERS
            resp = self.tcp.exec_command(cmd, None, 1.5)

            # here is when the magic happens - transform TCP JSON data into API channel representation
            receiver_channels = self._get_channels_int(resp)

            cmd = self.CMD_FETCH_SENSORS
            resp = self.tcp.exec_command(cmd, None, 1)
            sensor_channels = self._get_channels_int(resp)

            cmd = self.CMD_FETCH_EXTAFREE
            resp = self.tcp.exec_command(cmd, None, 1)
            extafree_channels = self._get_channels_int(resp)

            channels = receiver_channels
            channels.extend(sensor_channels)
            channels.extend(extafree_channels)

            return channels

        except TCPCmdError:
            log.error("Command %s could not be executed", cmd)
            return None

    @classmethod
    def _get_channels_int(cls, data_js):
        """
        data_js - list of TCP command data in JSON dict

        The method will transform TCP JSON into list of channels.
        Each channel will look like rephrased TCP JSON and will consist of attributes
        of the "state" section (channel) + attributes of the "device" section
        eg.:
        "devices": [{
				"id": 11,
				"is_powered": false,
				"is_paired": false,
				"set_remove_sensor": false,
				"device": 1,
				"type": 11,
				"serial": 725149,
				"state": [{
						"alias": "Kuchnia 1-1",
						"channel": 1,
						"icon": 13,
						"is_timeout": false,
						"fav": null,
						"power": 0,
						"last_dir": null,
						"value": null
					}
				]
			}
        will become:
            [
                "channel": "11-1",
                "data":
                {
                    "alias": "Kuchnia 1-1",
                    "channel": 1,
                    "icon": 13,
                    "is_timeout": false,
                    "fav": null,
                    "power": 0,
                    "last_dir": null,
                    "value": null,
                    "id": 11,
                    "is_powered": false,
                    "is_paired": false,
                    "set_remove_sensor": false,
                    "device": 1,
                    "type": 11,
                    "serial": 725149
                }

        ]
        """
        channels = []  # list of JSON dicts
        for cmd in data_js:
            for device in cmd["data"]["devices"]:
                dev = device.copy()
                dev.pop("state")
                for state in device["state"]:
                    channel = {
                        # API channel, not TCP channel
                        "id": str(device["id"]) + "-" + str(state["channel"]),
                        "data": {**state, **dev},
                    }
                    channels.append(channel)
        return channels

    def execute_action(self, action, channel_id, **fields):
        """Execute action/command in controller
        action - action to be performed. See ACTN_* constants
        channel_id - concatenation of device id and channel number e.g. '1-1'
        **fields - fields of the native JSON command e.g. value, mode, mode_val etc
        """
        MAP_ACION_STATE = {
            ExtaLifeAPI.ACTN_TURN_ON: 1,
            ExtaLifeAPI.ACTN_TURN_OFF: 0,
            ExtaLifeAPI.ACTN_OPEN: 1,
            ExtaLifeAPI.ACTN_CLOSE: 0,
            ExtaLifeAPI.ACTN_STOP: 2,
            ExtaLifeAPI.ACTN_SET_POS: None,
            ExtaLifeAPI.ACTN_SET_RGT_MODE_AUTO: 0,
            ExtaLifeAPI.ACTN_SET_RGT_MODE_MANUAL: 1,
            ExtaLifeAPI.ACTN_SET_TMP: 1,
            ExtaLifeAPI.ACTN_EXFREE_TURN_ON_PRESS: 1,
            ExtaLifeAPI.ACTN_EXFREE_TURN_ON_RELEASE: 2,
            ExtaLifeAPI.ACTN_EXFREE_TURN_OFF_PRESS: 3,
            ExtaLifeAPI.ACTN_EXFREE_TURN_OFF_RELEASE: 4,
        }
        ch_id, channel = channel_id.split("-")
        ch_id = int(ch_id)
        channel = int(channel)

        cmd_data = {
            "id": ch_id,
            "channel": channel,
            "state": MAP_ACION_STATE.get(action),
        }
        # this assumes the right fields are passed to the API
        cmd_data.update(**fields)

        try:
            cmd = self.CMD_CONTROL_DEVICE
            resp = self.tcp.exec_command(cmd, cmd_data, 0.2)

            log.debug("JSON response for command %s: %s", cmd, resp)

            return resp
        except TCPCmdError:
            log.error("Command %s could not be executed", cmd)
            return None

    def restart(self):
        """ Restart EFC-01 """
        try:
            cmd = self.CMD_RESTART
            cmd_data = dict()

            resp = self.tcp.exec_command(cmd, cmd_data, 0.2)

            log.debug("JSON response for command %s: %s", cmd, resp)

            return resp
        except TCPCmdError:
            log.error("Command %s could not be executed", cmd)
            return None

    def get_tcp_adapter(self):
        return self.tcp

    def get_notif_listener(self, on_notify):
        """
        Return Notification listener object wrapping 2nd TCP connection for notifications exclusively
        """
        return NotifThreadListener(self.host, self.user, self.password, on_notify)


class TCPConnError(Exception):
    pass


class TCPCmdError(Exception):
    pass


class TCPAdapter:

    TCP_BUFF_SIZE = 8192
    EFC01_PORT = 20400

    def __init__(self, user, password, host=None):
        self.user = user
        self.password = password
        self.host = None

        self.tcp = None
        # self.connect()

    def connect(self, host):
        """
        Connect to EFC-01 via TCP socket + try to log on via command: 1
        return json dictionary with result or exception in case of connection or logon
        problem
        """
        self.tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        self.host = host
        try:
            self.tcp.connect((self.host, self.EFC01_PORT))

            cmd_data = {"password": self.password, "login": self.user}
            resp_js = self.exec_command(ExtaLifeAPI.CMD_LOGIN, cmd_data)
            return resp_js

            # ################ IMPLEMENT CHECKING OF THE RESPONSE!!!!!!!
        except (Exception):
            # something wrong happend with the socket
            log.exception("Unexpected socket error")

            # cast to TCPConnError, but keep the original info
            raise TCPConnError

    @staticmethod
    def discover_controller():
        """
        Perform controller autodiscovery using UDP query
        return IP as string or false if not found
        """
        MCAST_GRP = "225.0.0.1"
        MCAST_PORT = 20401
        import struct

        # sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server_address = ("", MCAST_PORT)

        # Create the socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Bind to the server address
        try:
            sock.bind(server_address)
        except (socket.error, OSError) as e:
            sock.close()
            sock = None
            log.error("Could not connect to receive UDP multicast from EFC-01 on port %s", MCAST_PORT)
            return False
        # Tell the operating system to add the socket to the multicast group
        # on all interfaces (join multicast group)
        group = socket.inet_aton(MCAST_GRP)
        mreq = struct.pack("4sL", group, socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

        sock.settimeout(3)
        try:
            data, address = sock.recvfrom(1024)
        except Exception:
            sock.close()
            return False
        sock.close()
        log.debug("Got multicast response from EFC-01: %s", str(data.decode()))
        if data == b'{"status":"broadcast","command":0,"data":null}\x03':
            return address[0]  # return IP - array[0]; array[1] is sender's port
        return False

    def _json_to_tcp(self, json_dict):
        stream = json.dumps(json_dict) + chr(3)
        return stream.encode()

    def _tcp_to_json(self, tcp_data, command=None):
        data = tcp_data.decode()
        # print(data)
        if data is not None:
            # log.debug("TCP data received for command %s: %s", command, data)
            if data[-1] == chr(3):
                data = data[:-1]
        return self.parse_tcp_response(data, command)

    def ping(self):
        """ Keep connection alive - ping"""
        cmd_ping = " " + chr(3)
        try:
            self.tcp.send(cmd_ping.encode())
        except Exception:
            log.error("Connectivity error during executing EFC-01 ping")
            try:
                # s.shutdown(socket.SHUT_RDWR)
                self.tcp.close()
            except Exception:
                log.exception("Exception while closing Socket after failed socket.send")
                return
            log.info("Reconnecting to EFC-01 on IP: %s", self.host)

            self.connect(self.host)
            self.tcp.send(cmd_ping.encode())

    def exec_command(self, command, data, timeout=0.2):
        """
        request - json: EFC-01 native TCP
        convert python JSON dict into TCP stream
        and send to socket
        """
        from datetime import datetime

        SOCK_TIMEOUT = 15  # let it run maximum for 15 seconds

        request = {"command": command, "data": data}
        cmd = self._json_to_tcp(request)

        log.debug("TCP command to execute: %s", cmd)

        self.tcp.setblocking(0)
        try:
            # first receive some potential data waiting for us from other connections broadcasted to all connected sessions
            self.tcp.recv(self.TCP_BUFF_SIZE)
        except socket.error:
            pass
        try:
            # and then send the command
            self.tcp.send(cmd)
        except Exception:
            log.exception(
                "Socket exception occured while executing controller command %s",
                command,
            )
            raise TCPCmdError

        resp = b""
        time = datetime.now()
        # optimize performance in socket non-blocking mode to avoid waiting for timeouts, which may be very long (seconds)
        # Exta Life controller sends data in chunks. Need to wait for complete set and check status=success or failure
        # after every attempt to read the data from socket.
        resp_js = list()
        while True:
            try:
                resp = resp + self.tcp.recv(self.TCP_BUFF_SIZE)
                # sometimes JSON data received from TCP are not complete yet (invalid JSON syntax)
                # and so JSN decoder fails. Need to try full JSON decoding after every TCP call
                try:
                    resp_js = self._tcp_to_json(resp, command)
                except json.decoder.JSONDecodeError:
                    # check for overall timeout
                    if (datetime.now() - time).seconds > SOCK_TIMEOUT:
                        break
                    continue

                log.debug("resp_js: %s", resp_js)
                if resp_js and resp_js[-1].get("status") in (
                    "success",
                    "failure",
                ):  # non-empty lists are rendered as True in Python - pylint warning
                    break
            except socket.error:
                # expected error due to nonblocking mode and no data found
                # check if this is not running too long; otherwise it'll hang the whole integration
                if (datetime.now() - time).seconds > SOCK_TIMEOUT:
                    break

        return resp_js

    def listen(self, timeout, toutcback):
        """
        Read data from socket until 1 single, full notification is received
        This is a blocking function (infinite loop), thus the timeout callback called every [timeout] seconds
        """
        from datetime import datetime
        time = datetime.now()
        self.tcp.setblocking(1)
        self.tcp.settimeout(1.5)        # work in blocking mode as otherwise we'll have high CPU load by the loop

        resp = b""
        resp_js = list()
        while True:
            try:
                if (datetime.now() - time).seconds >= timeout:
                    # call the callback to perform other things while waiting for the notification
                    toutcback()
                    time = datetime.now()

                resp_1 = self.tcp.recv(self.TCP_BUFF_SIZE)
                # print(f"listen_once receiving: {resp_1}")
                if not resp_1:
                    continue
                resp = resp + resp_1
                # sometimes JSON data received from TCP are not complete yet (invalid JSON syntax)
                # and so JSON decoder fails. Need to try full JSON decoding after every TCP call
                try:
                    resp_js = self._tcp_to_json(resp)
                except json.decoder.JSONDecodeError:
                    continue

                log.debug("resp_js (intermediary): %s", resp_js)

                if resp_js and resp_js[-1].get("status") == "notification":
                    break
                pass
            except socket.error:
                pass

        return resp_js[0]

    @classmethod
    def filter_tcp_response(cls, tcp_js, command):
        """
        command - string constant
        stream  - TCP stream (String)

        Filter out unexpected TCP response data
        e.g. commands from other users/connections
        """
        # TODO: apply filter based on command type. eg command 20 (control) returns "notification" message and then "success" message
        data = []
        for elem in tcp_js:
            if elem["command"] == command:
                data.append(elem)
        return data

    @classmethod
    def parse_tcp_response(cls, tcp_data, command=None):
        """
        1. reformat TCP JSON into valid JSON (concatenate the "searching" parts)
        2. return TCP reformatted JSON
        """

        # array
        data_split = tcp_data.split("\3")
        if data_split[-1][-1] == "\n":
            data_split.pop()  # delete empty array element

        # need to enclose TCP JSON within []
        reform = "["
        c = 0
        for elem in data_split:
            c += 1
            sep = "," if c < len(data_split) else ""
            reform += elem + sep
        reform += "]"

        # once the TCP was reformatted - create pythonic JSON dict
        tcp_js = json.loads(reform)

        # filter rubbish data coming from other users and connections
        if command:
            tcp_js = cls.filter_tcp_response(tcp_js, command)

        # now, combine all "device" parts of the JSON dict into one list and return it to the caller
        return tcp_js


class NotifThreadListener(threading.Thread):
    """ Threaded TCP status update notifications listener """

    def __init__(self, host, user, password, on_notify):
        threading.Thread.__init__(self)
        self._user = user
        self._password = password
        self._host = host
        self._on_notify = on_notify

        self.connection = TCPAdapter(self._user, self._password)
        self.connection.connect(self._host)

    def run(self):
        while True:
            resp = self.connection.listen(9, self.ping)
            if resp:
                self._on_notify(resp)

    def ping(self):
        """ Keep connection alive """
        self.connection.ping()
