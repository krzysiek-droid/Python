import sys

from PyQt6 import QtWidgets, QtCore, QtGui
from PyQt6.uic import loadUi
import pyqtgraph as graph
import pandas
import random as rnd
from datetime import datetime

import time

freq_translation = {0: 4, 1: 10, 2: 33, 3: 50, 4: 62, 5: 123}


def timestamp():
    return datetime.now().timestamp()


class TimeAxisItem(graph.AxisItem):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setLabel(text='Time', units=None)
        self.enableAutoSIPrefix(False)
        self.setStyle(tickTextWidth=0)
        self.setScale(10)

    def tickStrings(self, values, scale, spacing):
        return [datetime.fromtimestamp(value).strftime("%H:%M:%S:%f")[:-5] for value in values]


class GraphWidget(graph.PlotWidget):
    def __init__(self, timeAxis: bool, *args, **kwargs):
        super(GraphWidget, self).__init__(*args, **kwargs)

        self.acquiredData = {'x_time': [], 'y_mass': []}

        self.timeAxis = TimeAxisItem(orientation='bottom')
        self.setAxisItems({'bottom': self.timeAxis})
        if not timeAxis:
            print(f'hiding time axis')
            self.getPlotItem().hideAxis('bottom')
        self.setBackground('w')
        self.setTitle(color="#ff0000", size="18pt")
        self.styles = {"color": "#ff0000", "font-size": "14px"}
        self.setLabel("left", "Measured mass (grams)", **self.styles)
        self.setLabel("bottom", "Hour (H)", **self.styles)
        # self.setYRange(600, 50)
        self.enableAutoRange(axis='y')
        self.setAutoVisible(y=True)

        self.x_axisPaddingTicks = 50
        self.x_axisData = [timestamp()]
        self.x_axisData.extend((timestamp() + 0.1) for _ in range(self.x_axisPaddingTicks - 1))
        self.y_axisData = [0.0 for _ in range(self.x_axisPaddingTicks)]
        self.pen = graph.mkPen(color='#ff0000', width=2)
        self.plotLineObj = self.plot(self.x_axisData, self.y_axisData, pen=self.pen)
        self.timer = QtCore.QTimer()
        self.timer.setInterval(1000)

    def livePlot_update(self, value_ref: QtWidgets.QLabel):
        timeStamp = timestamp()
        self.x_axisData = self.x_axisData[1:]
        self.x_axisData.append(timeStamp)
        self.y_axisData = self.y_axisData[1:]
        self.y_axisData.append(round(float(value_ref.text().replace(' g', ''))))
        self.plotLineObj.setData(self.x_axisData, self.y_axisData)

    def record_plot(self, value_ref: QtWidgets.QLabel):
        if len(self.x_axisData) <= 10000:
            timeStamp = timestamp()
            value = float(value_ref.text().replace(' g', ''))
            # update plot
            self.x_axisData.append(timeStamp)
            self.y_axisData.append(value)
            self.plotLineObj.setData(self.x_axisData, self.y_axisData)
            # update DataObject
            self.acquiredData['x_time'].append(datetime.fromtimestamp(timeStamp).strftime("%H:%M:%S:%f")[:-5])
            self.acquiredData['y_mass'].append(value)

        else:
            self.timer.stop()
            raise TimeoutError and print(f'Collected over 10 000 points of data!')

    def save_recording(self):
        df = pandas.DataFrame.from_dict(self.acquiredData)
        print(df)
        fileName, _ = QtWidgets.QFileDialog.getSaveFileName(self, "QFileDialog.getSaveFileName()", "",
                                                            "csv (*.csv)")
        if fileName:
            print(f"Saving at {fileName}")
            df.to_csv(path_or_buf=fileName, sep=';')
            print(f"File saved.")

    def discard_recording(self):
        self.clear()

    def reset_data(self):
        self.x_axisData = [timestamp()]
        self.x_axisData.extend((timestamp() + 0.1) for _ in range(self.x_axisPaddingTicks - 1))
        self.y_axisData = [0 for _ in range(self.x_axisPaddingTicks)]
        self.acquiredData['x_time'] = []
        self.acquiredData['y_mass'] = []
        self.plotLineObj = self.plot(self.x_axisData, self.y_axisData, pen=self.pen)
        self.timer = QtCore.QTimer()


class MassScaleMonitor(QtWidgets.QMainWindow):
    def __init__(self, *args, **kwargs):
        super(MassScaleMonitor, self).__init__(*args, **kwargs)
        self.mass_readout_precision = None
        self.liveTimer = None
        loadUi('uis/mainWindow_UI.ui', self)
        # self.dataPool = {'x_time': [], 'y_mass': []}
        self.dataPool_maxLength = 10000
        self.readOutLoop = QtCore.QTimer()
        # -------------------------------------------------------------- MODBUS Connection
        self.modbusConfig = {
            'conn_mthd': 'rtu',
            'port': 'COM3',
            'timeout': 1,
            'stopbits': 1,
            'bytesize': 8,
            'parity': 'N',
            'baudrate': 19200
        }
        from modbusConnection import ModbusClient
        self.modbusClient = None
        self.saveConfirmationFrame.hide()
        self.plotTabWidget.setTabEnabled(1, False)
        # ------------------------------------------------------------------------------ Btns scripts
        self.startRecordingBtn.clicked.connect(self.start_recordingData)
        self.connectToModbusBtn.clicked.connect(self.connectToModbus)
        # ------------------------------------------------------------------------------ Plot timing object

    def connectToModbus(self):
        from modbusConnection import ConfigDialog
        dialog = ConfigDialog()
        self.setEnabled(False)
        x = dialog.exec()
        self.setEnabled(True)

        print(f"status {dialog.status}, client {dialog.modbusClient}")
        if dialog.status:
            self.connStatusLbl.setText(f"Receiving data...")
        from modbusConnection import ModbusClient
        self.modbusClient: ModbusClient = dialog.modbusClient
        self.connectToModbusBtn.setChecked(True)
        self.connectToModbusBtn.setText('Connected')

        self.modbusClient.update_intInfo()
        self.modbusClient.update_realInfo()
        self.modbusClient.update_oneBits()

        self.ratedOutputLbl.setText(f"{round(self.modbusClient.realInfo['Real rated output'], 4)} mv/V")
        self.sensorRangeLbl.setText(f"{self.modbusClient.intInfo['Sensor capacity']} N")

        #   sampling frequency combo box setup
        self.samplingFreqCombo.setEditable(True)
        self.samplingFreqCombo.lineEdit().setReadOnly(True)
        self.samplingFreqCombo.lineEdit().setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.samplingFreqCombo.addItems([f"{freq_translation[key]} /s" for key in freq_translation.keys()])
        self.samplingFreqCombo.setCurrentIndex(
            list(freq_translation.values()).index(self.modbusClient.intInfo['Sampling frequency']))
        self.samplingFreqToolBtn.clicked.connect(lambda: self.samplingFreqToolBtn.setEnabled(True))
        self.samplingFreqToolBtn.clicked.connect(lambda: print('ADD FUNCTION FOR FREQ CHANGE - interval!'))  # TODO func
        self.sensRangeToolBtn.clicked.connect(lambda: print('ADD FUNCTION FOR range'))
        self.ratedOutputToolBtn.clicked.connect(lambda: print('ADD FUNCTION FOR ratedoutput'))

        self.liveTimer = QtCore.QTimer()
        self.liveTimer.timeout.connect(self.update_liveData)  # Update function (loop)
        self.liveTimer.setInterval(int(1000 / self.modbusClient.intInfo['Sampling frequency']))
        print(f"readout frequency set to {int(1000 / self.modbusClient.intInfo['Sampling frequency'])}")
        # decimal places combo setup
        self.decimalCombo.setEditable(True)
        self.decimalCombo.lineEdit().setReadOnly(True)
        self.decimalCombo.lineEdit().setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.decimalCombo.addItems([f"{_}" for _ in range(4)])

        self.decimalCombo.currentIndexChanged.connect(lambda x: self.change_readOutPrecision(int(x)))
        self.decimalCombo.setCurrentIndex(1)

        self.rawSignalTare.setText('0')

        self.tareBtn.clicked.connect(
            lambda: (self.rawSignalTare.setText(str(self.modbusClient.intInfo['Current RAW signal'])),
                     self.modbusClient.send_request(tare=True)))
        self.minMaxResetBtn.clicked.connect(lambda: self.modbusClient.send_request(reset_min_max=True))

        self.liveTimer.start()
        self.start_registering()

    def change_readOutPrecision(self, value):
        self.mass_readout_precision = value


    def update_liveData(self):
        received_intData = self.modbusClient.update_intInfo()
        received_realdData = self.modbusClient.update_realInfo()
        received_discrete = self.modbusClient.update_oneBits()

        actual_mass_readOut = round(float(received_realdData['Actual mass']), self.mass_readout_precision)
        self.actualMass.setText(f"{actual_mass_readOut} g")

        self.minLbl.setText(f"{round(received_realdData['Minimum registered real force'], 1)} g")
        self.maxLbl.setText(f"{round(received_realdData['Maximum registered real force'], 1)} g")

        rawSignalSubtraction = int(received_intData['Current RAW signal']) - int(self.rawSignalTare.text())
        self.massFromRawTare.setText(f"{round(rawSignalSubtraction*self.modbusClient.mass_scaleFromRaw, 2)} g")

        self.actualRawSignal.setText(f"RAW: {received_intData['Current RAW signal']} "
                             f"({round(received_intData['Current RAW signal'] * self.modbusClient.mV_scale, 3)} mV)")

        sensor_load = (int(received_intData['Current RAW signal']) / self.modbusClient.maximum_raw_signal) * 100
        self.progressBar.setValue(int(sensor_load))

        self.stabilityBtn.setText("Stable") if received_discrete['stability'] else self.stabilityBtn.setText("Unstable")
        self.stabilityBtn.setChecked(False) if received_discrete['stability'] else self.stabilityBtn.setChecked(True)

        self.overloadErrBtn.setChecked(False) if not received_discrete[
            'overload_conn error'] else self.overloadErrBtn.setChecked(True)
        self.overloadErrBtn.setText(f"OK") if not received_discrete[
            'overload_conn error'] else self.overloadErrBtn.setText(f"ERROR")

        self.converterErrBtn.setChecked(False) if not received_discrete[
            'general error'] else self.converterErrBtn.setChecked(True)
        self.converterErrBtn.setText(f"OK") if not received_discrete[
            'general error'] else self.converterErrBtn.setText(f"ERROR")

    def start_registering(self):
        livePlot = GraphWidget(timeAxis=False)
        livePlot.setTitle("Mass measurements in time", color='#ff0000', size='16pt')
        self.plotFreqSlider.setEnabled(True)
        self.refreshingRateFrame.hide()  # TODO: redesign slider to sampling frequency!
        # self.plotFreqSlider.valueChanged.connect(lambda value: (livePlot.timer.setInterval(int(1000 / value)),
        #                                                         self.plotFreqLbl.setText(f"{value} /s")))
        # self.plotFreqSlider.setValue(3)
        self.livePlotFrameLayout.addWidget(livePlot)
        livePlot.timer.timeout.connect(lambda: livePlot.livePlot_update(self.actualMass))
        livePlot.timer.setInterval(int(1000 / self.modbusClient.intInfo['Sampling frequency']))
        livePlot.timer.start()

    def start_recordingData(self):
        self.plotTabWidget.setTabEnabled(1, True)
        self.plotTabWidget.setCurrentIndex(1)
        if self.recordedTab.findChild(GraphWidget, 'recordedPlotWidget') is not None:
            # Update already existing plot
            print(f"found recordedPlot at {self.recordedTab.findChild(GraphWidget, 'recordedPlotWidget')}")
            recordedPlot = self.recordedTab.findChild(GraphWidget, 'recordedPlotWidget')
            recordedPlot.reset_data()
            recordedPlot.timer.timeout.connect(lambda: (recordedPlot.record_plot(self.actualMass),
                                                        self.update_recordedInfo(recordedPlot.acquiredData['x_time'],
                                                                                 recordedPlot.acquiredData['y_mass'])))
            recordedPlot.timer.setInterval(int(1000 / self.modbusClient.intInfo['Sampling frequency']))
        else:
            # Create the plot (first run)
            recordedPlot = GraphWidget(timeAxis=True)
            recordedPlot.setObjectName('recordedPlotWidget')
            recordedPlot.setTitle("Recorded mass measurements in time", color='#ff0000', size='16pt')
            self.acquiredPlotFrameLayout.addWidget(recordedPlot)
            recordedPlot.timer.timeout.connect(lambda: (recordedPlot.record_plot(self.actualMass),
                                                        self.update_recordedInfo(recordedPlot.acquiredData['x_time'],
                                                                                 recordedPlot.acquiredData['y_mass'])))

        recordedPlot.timer.setInterval(int(1000 / self.modbusClient.intInfo['Sampling frequency']))
        print(f"Recorded plot timer set to: {int(1000 / self.modbusClient.intInfo['Sampling frequency'])}")

        recordedPlot.timer.start()
        print(f"Started registering at {datetime.fromtimestamp(timestamp())}")

        self.stopRecordingBtn.clicked.connect(lambda: (recordedPlot.timer.stop(),
                                                       self.saveConfirmationFrame.show()))
        self.discardRecordingBtn.clicked.connect(lambda: self.discard_recordedPlot(recordedPlot))
        self.saveRecordingBtn.clicked.connect(lambda: (recordedPlot.save_recording(),
                                                       self.discard_recordedPlot(recordedPlot)))

    def update_recordedInfo(self, x_values, y_values, clear: bool = False):
        if len(x_values) > 2 and not clear:
            d1 = datetime.strptime(x_values[-1], "%H:%M:%S:%f")
            d2 = datetime.strptime(x_values[0], "%H:%M:%S:%f")
            self.acquiredMinLbl.setText(str(min(y_values)))
            self.acquiredMaxLbl.setText(str(max(y_values)))
            self.acquiredDurationLbl.setText(f"{(d1 - d2).total_seconds()} s")
            self.acquiaredPointsLbl.setText(str(len(x_values)))
        else:
            self.acquiredMinLbl.setText("-------")
            self.acquiredMaxLbl.setText("-------")
            self.acquiredDurationLbl.setText("-------")
            self.acquiaredPointsLbl.setText("-------")

    def discard_recordedPlot(self, plotObj: GraphWidget):
        plotObj.discard_recording()
        self.update_recordedInfo([], [], True)
        self.saveConfirmationFrame.hide()
        self.plotTabWidget.setCurrentIndex(0)
        self.plotTabWidget.setTabEnabled(1, False)

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    mainWindow = MassScaleMonitor()

    mainWindow.show()
    sys.exit(app.exec())
