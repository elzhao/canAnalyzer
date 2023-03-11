# coding:utf-8

import time
import os
import threading
from queue import Queue
from PyQt5.QtWidgets import QWidget, QMessageBox, QHeaderView
from PyQt5 import Qt, QtCore, QtWidgets
from PyQt5.QtCore import qDebug

import ui_widget
from canmsgtablemodel import CanMsgTableModel
from mycombobox import MyComboBox
from can.interfaces.bmcan import BmCanBus
import can
from canio.trc import TRCReader, TRCWriter

tr = QtCore.QCoreApplication.translate
COUNT = 4 #channel count

class Widget(QWidget, ui_widget.Ui_Widget):
    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.txIdEdits   = [self.txIdEdit, self.txIdEdit_2, self.txIdEdit_3, self.txIdEdit_4]
        self.txFdChecks  = [self.txFdCheck, self.txFdCheck_2, self.txFdCheck_3, self.txFdCheck_4]
        self.txExChecks  = [self.txExtendedCheck, self.txExtendedCheck_2, self.txExtendedCheck_3, self.txExtendedCheck_4]
        self.txCycEdits  = [self.txCycleEdit, self.txCycleEdit_2, self.txCycleEdit_3, self.txCycleEdit_4]
        self.txCouEdits  = [self.txCountEdit, self.txCountEdit_2, self.txCountEdit_3, self.txCountEdit_4]
        self.txDlcEdits  = [self.txDlcEdit, self.txDlcEdit_2, self.txDlcEdit_3, self.txDlcEdit_4]
        self.txDataEdits = [self.txDataEdit, self.txDataEdit_2, self.txDataEdit_3, self.txDataEdit_4]
        self.txButtons   = [self.txButton, self.txButton_2, self.txButton_3, self.txButton_4]

        self.txButton.clicked.disconnect()
        for btn in self.txButtons:
            btn.setCheckable(False)
            btn.clicked.connect(self.on_txButton_clicked)

        self.openButton.setCheckable(False)
        self.openButton.clicked.disconnect()
        self.openButton.clicked.connect(self.on_openButton_clicked)
        self.enumerateButton.setCheckable(False)
        self.enumerateButton.clicked.disconnect()
        self.enumerateButton.clicked.connect(self.on_enumerateButton_clicked)
        self.recordCheck.clicked.disconnect()
        self.recordCheck.clicked.connect(self.on_recordCheck_clicked)
        self.sendButton.setCheckable(False)
        self.sendButton.clicked.connect(self.on_sendFile_clicked)
        self.stopButton.setCheckable(False)
        self.stopButton.clicked.connect(self.on_stopSend_clicked)
        self.modeCombo.addItem("Normal")
        self.modeCombo.addItem("Classic")
        self.modeCombo.addItem("Loopback")
        self.modeCombo.addItem("ListenOnly")

        self.msgTableModel = CanMsgTableModel()
        self.msgTableView.setModel(self.msgTableModel)
        self.msgTableView.horizontalHeader().setSectionResizeMode(self.msgTableView.horizontalHeader().count() - 1, QHeaderView.Stretch)

        self.isOpened = False
        self.isTransmitting = False
        self.pendingTxMsgCount = 0
        self.recordFile = None
        self.recordFlag = False
        self.isSendingFile = False

        self.rxTimer = QtCore.QTimer()
        self.txTimer = QtCore.QTimer()
        self.txTimer_2 = QtCore.QTimer()
        self.txTimer_3 = QtCore.QTimer()
        self.txTimer_4 = QtCore.QTimer()
        self.sendFileTimer = QtCore.QTimer()

        self.txTimers = [self.txTimer, self.txTimer_2, self.txTimer_3, self.txTimer_4]
        for timer in self.txTimers:
            timer.timeout.connect(self.writePendingMessages)

        self.rxTimer.timeout.connect(self.readPendingMessages)
        self.sendFileTimer.timeout.connect(self.writeFileMessages)

        self.sendQueue = Queue()
        self.channelhandles = {}
        self.pendingTxMsgs = [0, 0, 0, 0]
        self.pendingTxMsgCounts = [0, 0, 0, 0]

        self.enumerate()

    def enumerate(self):
        self.channels = BmCanBus.enumerate()
        self.channelCombo.clear()
        for channel in self.channels:
            self.channelCombo.add_item(channel['name'])

    def readPendingMessages(self):
        newMsgInserted = False
        for index in range(len(self.channelhandles)):
            if (self.channelhandles[index] and self.msgTableModel):
                while True:
                    try:
                        msg = self.channelhandles[index].recv(timeout=0)
                    except:
                        msg = None
                        pass
                    if msg is not None: # Return None indicates timeout condition
                        self.msgTableModel.insertMessage(msg, index + 1)
                        newMsgInserted = True
                        if self.recordFlag:
                            self.recordFile.on_message_received(msg)
                    else:
                        break
            if (newMsgInserted):
                self.msgTableView.scrollToBottom()

    def writePendingMessages(self):
        index = -1
        for i in range(COUNT):
            if self.txTimers[i] == self.sender():
                index = i
                break
        if index >= 0:
            self.writePendingMessagesIndex(index)

    def writePendingMessagesIndex(self, index):
        if self.sendCanMessage(self.pendingTxMsgs[index], index):
            self.pendingTxMsgCounts[index] -= 1
            if (self.pendingTxMsgCounts[index] <= 0):
                self.stopSend(index)
            ackMsg = self.pendingTxMsgs[index]
            ackMsg.timestamp = time.time()
            ackMsg.is_ack = True
            self.msgTableModel.insertMessage(ackMsg, index + 1)
            self.msgTableView.scrollToBottom()

    def sendCanMessage(self, msg, index):
        try:
            self.channelhandles[index].send(msg, timeout=0.5)
            return True
        except Exception as exc:
            qDebug(str(exc))
            return False

    def writeFileMessages(self):
        if not self.isSendingFile and self.sendQueue.empty():
            self.sendFileTimer.stop()
            return
        msgList = []
        insertList = []
        while(not self.sendQueue.empty()):
            msgList.append(self.sendQueue.get_nowait())

        for msg in msgList:
            index = msg.channel - 1
            if index >= 0 and self.sendCanMessage(msg, index):
                msg.timestamp = time.time()
                msg.is_ack = True
                msg.port = index + 1
                msg.channel = None
                insertList.append(msg)
        if len(insertList) > 0:
            self.msgTableModel.insertMessageList(insertList)
            self.msgTableView.scrollToBottom()

    def on_recordCheck_clicked(self):
        if not self.recordCheck.isChecked():
            self.recordFlag = False
            return
        desk_path = os.path.join(os.path.expanduser("~"), 'Desktop')
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(self,
              "File Save As", desk_path, "Record File (*.trc);;All Files (*)")
        print('record File: ', file_path)
        if len(file_path) == 0:
            self.recordCheck.setCheckState(False)
        else:
            self.recordFile = TRCWriter(file_path)
            self.recordFile.write_header(time.time())
            self.recordFlag = True

    def on_sendFile_clicked(self):
        desk_path = os.path.join(os.path.expanduser("~"), 'Desktop')
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(self,
              "Open File", desk_path, "Send File (*.trc);;All Files (*)")
        # file_path = 'C:\\Users\\william\Desktop\\3.trc'
        if self.isOpened and len(file_path) > 0:
            self.stopButton.setEnabled(True)
            send_thread = threading.Thread(target=self.sendFile, args=(file_path,))
            send_thread.start()
            self.sendButton.setEnabled(False)
            self.sendFileTimer.start(10)

    def sendFile(self, file_path):
        self.isSendingFile = True
        trc_read = TRCReader(file_path)
        old_msg = None
        old_time = time.time()
        for msg in trc_read:
            if not self.isSendingFile:
                break
            if old_msg is None:
                #print((time.time() - old_time), msg)
                # self.sendCanMessage(msg)
                self.sendQueue.put(msg)
            else:
                wait_time = msg.timestamp - (time.time() - old_time)
                wait_time = 0 if wait_time < 0 else wait_time
                time.sleep(wait_time)
                #print((time.time() - old_time), msg)
                # self.sendCanMessage(msg)
                self.sendQueue.put(msg)
            old_msg = msg
        self.sendButton.setEnabled(True)
        self.stopButton.setEnabled(False)
        self.isSendingFile = False

    def on_stopSend_clicked(self):
        self.isSendingFile = False
        self.stopButton.setEnabled(False)

    def on_openButton_clicked(self):
        success = True
        for i in range(COUNT):
            self.channelhandles[i] = None
        if not self.isOpened:
            if not self.channels:
                QMessageBox.critical(None, "Error", "Please plugin your Busmust device and press 'Enumerate'.")
                success = False
            for index in range(len(self.channels)):
                if self.channelCombo.isChecked(index):#被勾选的子项
                    channel = self.channels[index]
                    mode = self.modeCombo.currentText().lower()
                    tres = self.tresCheck.isChecked()
                    nbitrate = int(self.nominalBitrateEdit.text())
                    dbitrate = int(self.dataBitrateEdit.text())
                    samplepos = int(self.samplePosSpin.value())
                    filters = []
                    if self.rxAdvancedFilterCheck.isChecked():
                        QMessageBox.critical(None, 'Error', 'Advanced filter is currently not supported by demo.', QMessageBox.Ok)
                    else:
                        rxid = int(self.rxIdEdit.text(), 16)
                        rxmask = int(self.rxMaskEdit.text(), 16)
                        rxstd = self.rxStandardCheck.isChecked()
                        rxext = self.rxExtendedCheck.isChecked()
                        if not rxstd and not rxext:
                            rxstd = True
                            rxext = True
                            self.rxStandardCheck.setChecked()
                            self.rxExtendedCheck.setChecked()
                        if rxstd:
                            filters.append({"can_id": rxid, "can_mask": rxmask, "extended": False})
                        if rxext:
                            filters.append({"can_id": rxid, "can_mask": rxmask, "extended": True})

                        try:
                            print('Open channel %s: nbitrate=%d, dbitrate=%d, tres=%s' % (channel['name'], nbitrate, dbitrate, str(tres)))
                            handle = BmCanBus(bustype='bmcan',
                                channel=channel['name'], bitrate=nbitrate * 1000, data_bitrate=dbitrate * 1000, tres=tres, 
                                fd='classic' not in mode, 
                                receive_own_messages='loopback' in mode,
                                listen_only='listen' in mode,
                                can_filters=filters
                            )
                            self.channelhandles[index] = handle
                        except Exception as exc:
                            QMessageBox.critical(None, 'Error', "Failed to open channel %s:\r\n%s" % (channel['name'], str(exc)), QMessageBox.Ok)
                            success = False
        else:
            self.stopAll()
            for i in range(COUNT):
                if self.channelhandles[i] is not None:
                    self.channelhandles[i].shutdown()
                    self.channelhandles[i] = None

        if not self.isOpened and success:
            #msgTableModel.clearAllMessages()
            self.rxTimer.start(50)
            self.openButton.setText(tr("Widget", "Close"))
            self.rxIdEdit.setEnabled(False)
            self.rxMaskEdit.setEnabled(False)
            self.rxExtendedCheck.setEnabled(False)
            self.rxStandardCheck.setEnabled(False)
            #self.rxAdvancedFilterCheck.setEnabled(False)
            self.rxDataMaskEdit.setEnabled(False)
            self.modeCombo.setEnabled(False)
            self.tresCheck.setEnabled(False)
            self.nominalBitrateEdit.setEnabled(False)
            self.dataBitrateEdit.setEnabled(False)
            self.samplePosSpin.setEnabled(False)
            self.enumerateButton.setEnabled(False)
            for i in range(COUNT):
                if self.channelhandles[i]:
                    self.txButtons[i].setEnabled(True)
            self.isOpened = True
            self.channelCombo.setEnabled(False)
            self.sendButton.setEnabled(True)
        else:
            self.rxTimer.stop()
            self.openButton.setText(tr("Widget", "Open"))
            self.rxIdEdit.setEnabled(True)
            self.rxMaskEdit.setEnabled(True)
            self.rxExtendedCheck.setEnabled(True)
            self.rxStandardCheck.setEnabled(True)
            #self.rxAdvancedFilterCheck.setEnabled(True)
            self.rxDataMaskEdit.setEnabled(self.rxAdvancedFilterCheck.isChecked())
            self.modeCombo.setEnabled(True)
            self.tresCheck.setEnabled(True)
            self.nominalBitrateEdit.setEnabled(True)
            self.dataBitrateEdit.setEnabled(True)
            self.samplePosSpin.setEnabled(True)
            self.enumerateButton.setEnabled(True)
            for i in range(COUNT):
                self.txButtons[i].setEnabled(False)
            self.isOpened = False
            self.channelCombo.setEnabled(True)
            self.sendButton.setEnabled(False)

    def on_enumerateButton_clicked(self):
        self.enumerate()

    def on_txButton_clicked(self):
        index = -1
        for i in range(COUNT):
            if self.txButtons[i] == self.sender():
                index = i
                break
        if (index >= 0):
            self.startOrStop(index)

    def startOrStop(self, index):
        if self.txTimers[index].isActive():
            self.stopSend(index)
        elif self.channelhandles[index]:
            dlc = int(self.txDlcEdits[index].text(), 10)
            data = bytes.fromhex(self.txDataEdits[index].text().replace(' ', ''))
            self.pendingTxMsgs[index] = can.Message(
                arbitration_id=int(self.txIdEdits[index].text(), 16),
                dlc=dlc,
                data=data[:dlc],
                is_extended_id=self.txExChecks[index].isChecked(),
                is_fd=self.txFdChecks[index].isChecked(),
                bitrate_switch=self.txFdChecks[index].isChecked(),
            )
            self.pendingTxMsgCounts[index] = int(self.txCouEdits[index].text())
            self.txTimers[index].start(int(self.txCycEdits[index].text()))
            self.txButtons[index].setText(tr("Widget", "Stop"))
            self.writePendingMessagesIndex(index)

    def stopAll(self):
        for index in range(COUNT):
            self.stopSend(index)

    def stopSend(self, index):
        self.txTimers[index].stop()
        self.pendingTxMsgCounts[index] = 0
        self.txButtons[index].setText(tr("Widget", "Transmit"))
