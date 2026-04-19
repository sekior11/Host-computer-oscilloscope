"""
200kHz 高速双通道示波器 Pro Max 界面实现

功能：
- 实时波形显示
- FFT 频谱分析
- 通道选择
- 触发电平调节
- 时间和幅度 DIV 调整
- 自动测量 (峰峰值、最大值、最小值、平均值)
- 数字滤波器设置
- 硬件状态显示

依赖：
- PySide6 (Qt 界面)
- pyqtgraph (波形绘制)
- numpy (数据处理)
- pyusb (USB 通信)
"""

import sys
import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout,
                               QVBoxLayout, QSlider, QDial, QLabel, QGroupBox,
                               QComboBox, QPushButton, QTabWidget, QFormLayout, QSpinBox)
from PySide6.QtCore import Qt, QTimer

# USB 依赖和硬件参数
import usb.core
import usb.util
import usb.backend.libusb1

# 1. 单片机 VID 和 PID
# VID: 厂商识别码
# PID: 产品识别码
VID = 0x1A86
PID = 0x5537
ENDPOINT_IN = 0x81  # 输入端点地址
READ_SIZE = 4096    # 每次读取的数据大小

# 2. 强行加载 libusb 驱动后端
backend = usb.backend.libusb1.get_backend(find_library=lambda x: r"E:\Python_project\QT\libusb-1.0.dll")

class ProfessionalOscilloscope(QMainWindow):
    """示波器主类
    
    实现了一个专业级示波器的用户界面和功能，包括：
    - 双通道数据采集和显示
    - 实时波形绘制
    - FFT 频谱分析
    - 各种控制参数调节
    """

    def __init__(self):
        """初始化示波器
        
        完成以下初始化工作：
        1. 设置窗口标题和大小
        2. 连接 USB 设备
        3. 配置 UI 布局和控件
        4. 初始化定时器
        """
        super().__init__()
        self.setWindowTitle("高速双通道示波器")
        self.resize(1200, 800)

        # --- 初始化 USB ---
        # 查找并连接 USB 设备
        self.dev = usb.core.find(idVendor=VID, idProduct=PID, backend=backend)
        if self.dev is None:
            raise ValueError("设备未找到！请检查 Zadig 驱动。")
        # 设置设备配置
        self.dev.set_configuration()
        print("成功连接到 200kHz 示波器！")

        # 核心：设置全局白色背景/浅色主题
        self.setStyleSheet("""
            QMainWindow { background-color: #F0F0F0; }
            QGroupBox { font-weight: bold; border: 1px solid #B0B0B0; margin-top: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px 0 3px; }
            QLabel { color: #333333; }
        """)

        # 创建主部件和水平总布局
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)

        # ==========================================
        # 1. 左侧面板：通道与触发控制
        # ==========================================
        left_panel = QVBoxLayout()

        # 通道选择
        ch_combo = QComboBox()
        ch_combo.addItems(["Channel 1 (PA1)", "Channel 2", "Dual Channel"])
        left_panel.addWidget(QLabel("通道选择:"))
        left_panel.addWidget(ch_combo)

        # 垂直滑块组 (模拟图中的幅度/频率条)
        slider_layout = QHBoxLayout()

        # 触发电平滑块
        trig_layout = QVBoxLayout()
        self.trig_slider = QSlider(Qt.Vertical)
        self.trig_slider.setRange(0, 4095)
        self.trig_slider.setValue(2048)
        trig_layout.addWidget(QLabel("触发电平"), alignment=Qt.AlignHCenter)
        trig_layout.addWidget(self.trig_slider, alignment=Qt.AlignHCenter)

        slider_layout.addLayout(trig_layout)
        left_panel.addLayout(slider_layout)

        # 偏移旋钮
        left_panel.addWidget(QLabel("Y轴偏移量:"))
        self.offset_dial = QDial()
        self.offset_dial.setRange(-2000, 2000)
        left_panel.addWidget(self.offset_dial)
        left_panel.addStretch()  # 把控件往上顶
        main_layout.addLayout(left_panel, stretch=1)  # 占比 1

        # ==========================================
        # 2. 中间面板：示波器主屏幕 + 大旋钮
        # ==========================================
        center_panel = QVBoxLayout()

        # 选项卡 (波形图, 频谱图等)
        self.tabs = QTabWidget()

        # 设置 pyqtgraph 为白底黑线风格
        pg.setConfigOption('background', 'w')
        pg.setConfigOption('foreground', 'k')

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.showGrid(x=True, y=True, alpha=0.5)
        self.plot_widget.setYRange(0, 3.5)
        self.plot_widget.setLabel('left', 'Voltage (V)')
        self.plot_widget.setLabel('bottom', 'Time (Samples)')

        # 画笔设置：红色波形，稍粗
        self.curve = self.plot_widget.plot(pen=pg.mkPen(color='r', width=2))

        self.fft_plot_widget = pg.PlotWidget()
        self.fft_plot_widget.showGrid(x=True, y=True, alpha=0.5)
        self.plot_widget.setMouseEnabled(x=False, y=False)
        self.fft_plot_widget.setLabel('left', 'Amplitude (V)', color='k')
        self.fft_plot_widget.setLabel('bottom', 'Frequency (kHz)', color='k')
        self.fft_plot_widget.setLogMode(x=False, y=False)  # 默认线性坐标，若需dB显示可后续开启
        # 使用深蓝色画笔，粗细为2
        self.fft_curve = self.fft_plot_widget.plot(pen=pg.mkPen(color='#1E90FF', width=2))

        self.tabs.addTab(self.plot_widget, "实时波形图")
        self.tabs.addTab(QWidget(), "滤波波形")
        self.tabs.addTab(self.fft_plot_widget, "FFT 频谱分析")

        center_panel.addWidget(self.tabs, stretch=4)

        # --- 底部大旋钮区 ---
        bottom_dials_layout = QHBoxLayout()

        # 1. 处理时间 DIV 布局
        time_div_layout = QVBoxLayout()
        self.time_dial = QDial()
        self.time_dial.setRange(50, 4000)
        self.time_dial.setValue(1000)
        self.time_dial.setNotchesVisible(True)
        time_div_layout.addWidget(QLabel("时间 DIV (X轴)"), alignment=Qt.AlignHCenter)
        time_div_layout.addWidget(self.time_dial)

        # 2. 处理幅度 DIV 布局
        amp_div_layout = QVBoxLayout()
        self.amp_dial = QDial()
        self.amp_dial.setRange(1, 200)
        self.amp_dial.setValue(50)
        self.amp_dial.setNotchesVisible(True)
        amp_div_layout.addWidget(QLabel("幅度 DIV (Y轴)"), alignment=Qt.AlignHCenter)
        amp_div_layout.addWidget(self.amp_dial)

        # 3. 封装
        bottom_dials_layout.addStretch()
        bottom_dials_layout.addLayout(time_div_layout)
        bottom_dials_layout.addLayout(amp_div_layout)
        bottom_dials_layout.addStretch()

        center_panel.addLayout(bottom_dials_layout, stretch=1)
        main_layout.addLayout(center_panel, stretch=6)

        # ==========================================
        # 3. 右侧面板：设置与采集控制
        # ==========================================
        right_panel = QVBoxLayout()

        # 滤波器设置组
        filter_group = QGroupBox("数字滤波器设置")
        filter_layout = QFormLayout()
        filter_layout.addRow("类型:", QComboBox())
        filter_layout.addRow("截止频率:", QSpinBox())
        filter_group.setLayout(filter_layout)
        right_panel.addWidget(filter_group)

        # 系统状态组
        sys_group = QGroupBox("硬件状态")
        sys_layout = QFormLayout()
        sys_layout.addRow("采样率:", QLabel("200.00 kHz"))
        sys_layout.addRow("单包数据量:", QLabel("4096 Bytes"))
        sys_group.setLayout(sys_layout)
        right_panel.addWidget(sys_group)

        # 控制按钮
        self.btn_start = QPushButton("▶ 开始采集 (Run)")
        self.btn_start.setMinimumHeight(50)
        self.btn_start.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; font-size: 14px;")

        self.btn_stop = QPushButton("⏹ 停止 (Stop)")
        self.btn_stop.setMinimumHeight(50)
        self.btn_stop.setStyleSheet("background-color: #F44336; color: white; font-weight: bold; font-size: 14px;")

        right_panel.addWidget(self.btn_start)
        right_panel.addWidget(self.btn_stop)
        right_panel.addStretch()

        # 测量数据组
        meas_group = QGroupBox("自动测量")
        meas_layout = QFormLayout()

        self.vpp_label = QLabel("0.00 V")
        self.vmax_label = QLabel("0.00 V")
        self.vmin_label = QLabel("0.00 V")
        self.vavg_label = QLabel("0.00 V")

        meas_layout.addRow("峰峰值 (Vpp):", self.vpp_label)
        meas_layout.addRow("最大值 (Vmax):", self.vmax_label)
        meas_layout.addRow("最小值 (Vmin):", self.vmin_label)
        meas_layout.addRow("平均值 (Vavg):", self.vavg_label)

        meas_group.setLayout(meas_layout)
        right_panel.addWidget(meas_group)  # 添加到右侧面板

        main_layout.addLayout(right_panel, stretch=2)  # 占比 2

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_wave)
        self.btn_start.clicked.connect(self.timer.start)
        self.btn_stop.clicked.connect(self.timer.stop)

        self.phase = 0

    def update_wave(self):
        """更新波形显示
        
        主要功能：
        1. 从 USB 设备读取原始数据
        2. 解析双通道 ADC 数据
        3. 转换为实际电压值
        4. 实现软件触发
        5. 根据设置调整显示参数
        6. 更新波形图
        7. 计算并显示测量数据
        8. 计算并显示 FFT 频谱
        """
        try:
            # 1. 读取原始数据
            raw_data = self.dev.read(ENDPOINT_IN, READ_SIZE, timeout=100)
            # 将原始数据转换为 uint32 数组
            raw_array = np.frombuffer(raw_data, dtype=np.uint32)
            # 提取通道 1 数据（低 16 位）
            adc1_wave = raw_array & 0x0000FFFF
            # 提取通道 2 数据（高 16 位）
            adc2_wave = (raw_array & 0xFFFF0000) >> 16
            # 将双通道数据合并为一维数组
            true_wave_raw = np.column_stack((adc2_wave, adc1_wave)).flatten()

            # 转换为 0~3.3V 原始电压
            real_voltage_wave = (true_wave_raw / 4095.0) * 3.3

            # 2. 【软件触发】定位起点
            # 计算触发电平对应的电压值
            trig_volts = self.trig_slider.value() * 3.3 / 4096
            # 找到上升沿触发点
            trigger_indices = np.where((real_voltage_wave[:-1] < trig_volts) &
                                       (real_voltage_wave[1:] >= trig_volts))[0]

            # 3. 【时间调整】根据 time_dial 决定显示多少个点
            points_to_show = self.time_dial.value()  # 获取旋钮值

            if len(trigger_indices) > 0:
                # 有触发点，从第一个触发点开始显示
                start_idx = trigger_indices[0]
                # 从触发点开始，截取固定长度
                display_wave = real_voltage_wave[start_idx: start_idx + points_to_show]
            else:
                # 若未触发，默认取开头一段
                display_wave = real_voltage_wave[:points_to_show]

            # 4. 【幅度调整】应用缩放和偏移
            # 这里的 y_scale 由 amp_dial 决定
            y_scale = self.amp_dial.value() / 50.0
            y_offset = self.offset_dial.value() / 1000.0

            # 以 1.65V (中点) 为中心进行缩放
            final_display = ((display_wave - 1.65) * y_scale) + 1.65 + y_offset

            # 5. 【绘图】
            self.curve.setData(final_display)

            # 6. 【测量数据更新】
            v_max, v_min = np.max(real_voltage_wave), np.min(real_voltage_wave)
            self.vmax_label.setText(f"{v_max:.2f} V")
            self.vpp_label.setText(f"{(v_max - v_min):.2f} V")
            self.vmin_label.setText(f"{v_min:.2f} V")
            self.vavg_label.setText(f"{np.mean(real_voltage_wave):.2f} V" )
            # 7. 【FFT 计算】使用原始数据以保持频率精度
            self.update_fft(real_voltage_wave)

        except usb.core.USBError:
            # 捕获 USB 错误，防止程序崩溃
            pass

    def update_fft(self, data):
        """更新 FFT 频谱显示
        
        功能：
        1. 对输入数据进行 FFT 变换
        2. 计算频率轴
        3. 绘制频谱图
        
        参数：
        data : numpy.ndarray
            输入的电压数据数组
        """
        # 将 FFT 逻辑拆分出来，保持代码整洁
        fs = 2000000.0  # 采样频率 (Hz)
        num_samples = len(data)  # 样本数量
        
        # 去除直流分量
        wave_ac = data - np.mean(data)
        
        # 计算 FFT 并归一化
        fft_mag = np.abs(np.fft.fft(wave_ac)) / num_samples * 2.0
        
        # 计算频率轴
        freq_axis = np.fft.fftfreq(num_samples, d=1.0 / fs)

        # 只取正频率部分
        half_n = num_samples // 2
        # 绘制频谱图（频率单位转换为 kHz）
        self.fft_curve.setData(freq_axis[:half_n] / 1000, fft_mag[:half_n])

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ProfessionalOscilloscope()
    window.show()
    sys.exit(app.exec())