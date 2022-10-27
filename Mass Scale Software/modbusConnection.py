import time

from pymodbus.client.sync import ModbusSerialClient
from pymodbus.payload import BinaryPayloadDecoder as mdsDecoder
from pymodbus.bit_read_message import ReadBitsResponseBase, ReadBitsRequestBase
from pymodbus.constants import Endian

from PyQt6 import QtWidgets, QtCore, QtGui
from PyQt6.uic import loadUi

import sys

import logging
FORMAT = ('%(asctime)-15s %(threadName)-15s '
          '%(levelname)-8s %(module)-15s:%(lineno)-8s %(message)s')
logging.basicConfig(format=FORMAT)
log = logging.getLogger()
#log.setLevel(logging.DEBUG)

intAddresses = {
    'Current force': 0,
    'Minimum registered force': 2,
    'Maximum registered force': 4,
    'Current RAW signal': 6,
    'Rated output': 8,
    'Sensor capacity': 10,
    'Sampling frequency': 12,
    'Analog output': 13,
    'Current force 2': 14,
    'Measurement stability': 15
}
realAddresses = {
    'Actual mass': 20,
    'Minimum registered real force': 22,
    'Maximum registered real force': 24,
    'Analog output real': 26,
    'Real rated output': 28
}
oneBitsReadRegisters={
    'input tara': 5000,
    'overload_conn error': 5001,
    'general error': 5002,
    'stability': 5003
}

class ModbusClient(ModbusSerialClient):
    def __init__(self, *args, **kwargs):
        super(ModbusClient, self).__init__(*args, **kwargs)
        self.intInfo = dict.fromkeys(intAddresses.keys(), 0)
        self.realInfo = dict.fromkeys(realAddresses.keys(), 0.0)
        self.oneBitsInfo = dict.fromkeys(oneBitsReadRegisters.keys(), 0)
        self.maximum_raw_signal = 3366      # calculated from WDT readouts
        self.mV_scale = 0.00078691347       #   calculated from WDT readouts
        self.mass_scaleFromRaw = 0.18355970571590265987549518958687

    def decode_toFloat(self, first_register_address) -> float:
        # first acquire 2 registers, first is low part of a real number, second is high part
        registers = self.read_holding_registers(address=first_register_address, count=2, unit=1).registers
        # Decode 2 acquired registers into single floating number with bits order [2,1,4,3] (Endian.Big + Endian.Little)
        decoder_obj = mdsDecoder.fromRegisters(registers, byteorder=Endian.Big, wordorder=Endian.Little)
        return decoder_obj.decode_32bit_float()

    def update_intInfo(self):
        curr_readout = self.read_holding_registers(address=0, count=16, unit=1)
        for key in self.intInfo.keys():
            self.intInfo[key] = curr_readout.registers[intAddresses[key]]

        freq_translation = {0: 4, 1: 10, 2: 33, 3: 50, 4:62, 5:123}
        self.intInfo['Sampling frequency'] = freq_translation[self.intInfo['Sampling frequency']]

        return self.intInfo

    def update_oneBits(self):
        # reading discrete inputs (1 Bit info), have to return bits[0] as a form of boolean value
        for key in self.oneBitsInfo.keys():
            self.oneBitsInfo[key] = self.read_discrete_inputs(address=oneBitsReadRegisters[key], count=1, unit=1).bits[0]
        return self.oneBitsInfo

    def update_realInfo(self):
        for key in self.realInfo.keys():
            self.realInfo[key] = self.decode_toFloat(realAddresses[key])
        return self.realInfo

    def send_request(self, tare=False, reset_min_max=False):
        if tare:
            x = self.write_coil(4000, True, unit=1)
            y = self.write_coil(4000, False, unit=1)
            print(f'Scale tared. {x} {y}')
        elif reset_min_max:
            x = self.write_coil(4001, True, unit=1)
            y = self.write_coil(4001, False, unit=1)
            print(f'Min/Max reseted. {x} {y}')

class ConfigDialog(QtWidgets.QDialog):
    def __init__(self):
        super(ConfigDialog, self).__init__()
        self.status = None
        loadUi('uis/cofigurationDialog_UI.ui', self)
        self.modbusConfig = {
            'conn_mthd': 'rtu',
            'port': 'COM3',
            'timeout': 1,
            'stopbits': 1,
            'bytesize': 8,
            'parity': 'N',
            'baudrate': 19200
        }
        self.widgets = {
            'port': self.portCombo,
            'timeout': self.timeoutLine,
            'parity': self.parityCombo,
            'baudrate': self.baudCombo
        }
        self.options = {
            'port': self.locate_usb(),
            'parity': ["None", "Odd", "Even"],
            'baudrate': ['9400', '19200', '38400', '57600', '115200']
        }
        self.modbusClient = None
        for key in self.widgets.keys():
            if type(self.widgets[key]) is QtWidgets.QComboBox:
                self.widgets[key].setEditable(True)
                self.widgets[key].lineEdit().setReadOnly(True)
                self.widgets[key].lineEdit().setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                self.widgets[key].addItems(self.options[key])
            elif type(self.widgets[key]) is QtWidgets.QLineEdit:
                self.widgets[key].setText('1')

        self.baudCombo.setCurrentText('19200')
        self.connectBtn.clicked.connect(lambda: (self.close() if self.connectModbus() else print(' ')))

    def locate_usb(self):
        from serial.tools import list_ports
        port_connected = list_ports.comports(include_links=False)
        portNames_list = []
        for port in port_connected:
            portNames_list.append(port.name)
        return portNames_list

    def connectModbus(self):
        self.modbusConfig['port'] = self.portCombo.currentText()
        self.modbusConfig['parity'] = self.parityCombo.currentText()[0].capitalize()
        self.modbusConfig['baudrate'] = int(self.baudCombo.currentText())
        self.modbusConfig['timeout'] = int(self.timeoutLine.text())
        self.modbusClient = ModbusClient(method=self.modbusConfig['conn_mthd'], port=self.modbusConfig['port'],
                                         timeout=self.modbusConfig['timeout'], stopbits=self.modbusConfig['stopbits'],
                                         bytesize=self.modbusConfig['bytesize'], parity=self.modbusConfig['parity'],
                                         baudrate=int(self.modbusConfig['baudrate']))
        print(f"connection to modbus, {self.modbusConfig}")
        self.statusLbl.setText(f"Connecting to modbus...")
        self.status = self.modbusClient.connect()
        self.statusLbl.setText("Connection established!") if self.status else self.statusLbl.setText("Connection failed.")

    def closeEvent(self, a0: QtGui.QCloseEvent):
        return self.modbusClient, self.status

if __name__ == "__main__":
    client = ModbusClient(method='rtu', port='COM3', timeout=3, stopbits=1, bytesize=8, parity='N', baudrate=19200)
    client.connect()
    y=0
    client.update_realInfo()
    print(client.realInfo)
    client.update_intInfo()
    print(client.intInfo)
    client.update_oneBits()
    print(client.oneBitsInfo)
