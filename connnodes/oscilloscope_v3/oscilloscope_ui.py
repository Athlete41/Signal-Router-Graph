"""
示波器 V3 — UI 布局定义

仅负责控件创建和布局，不包含任何信号连接。
参数命名参考 <总体.md> 四的用户参数表。
"""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import (QCheckBox, QDoubleSpinBox, QFormLayout,
                              QGroupBox, QHBoxLayout, QLabel, QPushButton,
                              QScrollBar, QSpinBox, QVBoxLayout)

from .heartbeat import HeartbeatWidget
from .waveform_view import WaveformView


class Ui_OscilloscopeV3(object):
    """示波器 V3 UI 布局 — 纯控件创建，不含信号连接"""

    def setupUi(self, Content) -> None:
        """在 Content 上构建所有控件"""
        layout = QVBoxLayout(Content)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # ── 波形显示区 ──
        self.waveform_view = WaveformView(Content)
        layout.addWidget(self.waveform_view)

        # ── 心跳控件（铺满 WaveformView，检测 paintEvent 是否触发）──
        self.heartbeat = HeartbeatWidget(self.waveform_view)

        # ── 水平滚动条（波形图下方） ──
        self.x_scroll_bar = QScrollBar(Qt.Horizontal, Content)
        layout.addWidget(self.x_scroll_bar)

        # ── 工具栏 ──
        bar = QHBoxLayout()
        self.stop_btn = QPushButton("启动", Content)
        self.stop_btn.setCheckable(True)
        icon = QIcon()
        icon.addPixmap(QPixmap("icons/active.png"), QIcon.Normal, QIcon.Off)
        icon.addPixmap(QPixmap("icons/deactive.png"), QIcon.Normal, QIcon.On)
        self.stop_btn.setIcon(icon)
        bar.addWidget(self.stop_btn)
        self.clear_btn = QPushButton("清理画面", Content)
        bar.addWidget(self.clear_btn)
        self.save_btn = QPushButton("保存数据", Content)
        bar.addWidget(self.save_btn)
        self.ch_select_btn = QPushButton("CH1", Content)
        self.ch_select_btn.setCheckable(True)
        self.ch_select_btn.setStyleSheet("color: #FFFF00;")
        bar.addWidget(self.ch_select_btn)
        bar.addStretch()
        layout.addLayout(bar)

        # ── 垂直系统（含 input 1 / input 2 子组）──
        vg = QGroupBox("垂直系统", Content)
        vg_layout = QVBoxLayout(vg)
        vg_layout.setSpacing(3)

        # 格数（垂直系统顶层）
        gf = QFormLayout()
        self.y_div_spin = QDoubleSpinBox(Content)
        self.y_div_spin.setRange(0.1, 100.0)
        self.y_div_spin.setDecimals(1)
        self.y_div_spin.setValue(8.0)
        self.y_div_spin.setSuffix(" 格")
        gf.addRow("格数:", self.y_div_spin)
        vg_layout.addLayout(gf)

        # ── input 1（CH1）子组 ──
        ig1 = QGroupBox("input 1", Content)
        ig1.setStyleSheet("QGroupBox { color: #FFFF00; border: 1px solid #555; border-radius: 4px; margin-top: 8px; font-weight: bold; } QGroupBox::title { color: #FFFF00; subcontrol-origin: margin; left: 8px; padding: 0 4px; }")
        i1f = QFormLayout(ig1)
        i1f.setSpacing(3)

        l1 = QLabel("范围:", Content)
        l1.setStyleSheet("color: #FFFF00;")
        self.y_window_mv_1_spin = QDoubleSpinBox(Content)
        self.y_window_mv_1_spin.setRange(0.1, 100_000.0)
        self.y_window_mv_1_spin.setDecimals(1)
        self.y_window_mv_1_spin.setValue(2000.0)
        self.y_window_mv_1_spin.setSuffix(" mV")
        self.y_window_mv_1_spin.setSingleStep(100.0)
        i1f.addRow(l1, self.y_window_mv_1_spin)

        l2 = QLabel("偏移:", Content)
        l2.setStyleSheet("color: #FFFF00;")
        self.y_offset_mv_1_spin = QDoubleSpinBox(Content)
        self.y_offset_mv_1_spin.setRange(-100_000, 100_000)
        self.y_offset_mv_1_spin.setDecimals(1)
        self.y_offset_mv_1_spin.setSuffix(" mV")
        i1f.addRow(l2, self.y_offset_mv_1_spin)

        ld1 = QLabel("div:", Content)
        ld1.setStyleSheet("color: #FFFF00;")
        self.ch1_div_label = QLabel("--", Content)
        self.ch1_div_label.setStyleSheet("color: #FFFF00;")
        i1f.addRow(ld1, self.ch1_div_label)

        vg_layout.addWidget(ig1)

        # ── input 2（CH2）子组 ──
        ig2 = QGroupBox("input 2", Content)
        ig2.setStyleSheet("QGroupBox { color: #00FFFF; border: 1px solid #555; border-radius: 4px; margin-top: 8px; font-weight: bold; } QGroupBox::title { color: #00FFFF; subcontrol-origin: margin; left: 8px; padding: 0 4px; }")
        i2f = QFormLayout(ig2)
        i2f.setSpacing(3)

        l3 = QLabel("范围:", Content)
        l3.setStyleSheet("color: #00FFFF;")
        self.y_window_mv_2_spin = QDoubleSpinBox(Content)
        self.y_window_mv_2_spin.setRange(0.1, 100_000.0)
        self.y_window_mv_2_spin.setDecimals(1)
        self.y_window_mv_2_spin.setValue(2000.0)
        self.y_window_mv_2_spin.setSuffix(" mV")
        self.y_window_mv_2_spin.setSingleStep(100.0)
        i2f.addRow(l3, self.y_window_mv_2_spin)

        l4 = QLabel("偏移:", Content)
        l4.setStyleSheet("color: #00FFFF;")
        self.y_offset_mv_2_spin = QDoubleSpinBox(Content)
        self.y_offset_mv_2_spin.setRange(-100_000, 100_000)
        self.y_offset_mv_2_spin.setDecimals(1)
        self.y_offset_mv_2_spin.setSuffix(" mV")
        i2f.addRow(l4, self.y_offset_mv_2_spin)

        ld2 = QLabel("div:", Content)
        ld2.setStyleSheet("color: #00FFFF;")
        self.ch2_div_label = QLabel("--", Content)
        self.ch2_div_label.setStyleSheet("color: #00FFFF;")
        i2f.addRow(ld2, self.ch2_div_label)

        vg_layout.addWidget(ig2)

        layout.addWidget(vg)

        # ── 水平系统（含 input 1 / input 2 子组）──
        hg = QGroupBox("水平系统", Content)
        hg_layout = QVBoxLayout(hg)
        hg_layout.setSpacing(3)

        # 顶层控件
        hf = QFormLayout()
        self.x_window_ms_spin = QDoubleSpinBox(Content)
        self.x_window_ms_spin.setRange(0.001, 100_000.0)
        self.x_window_ms_spin.setDecimals(3)
        self.x_window_ms_spin.setValue(1000.0)
        self.x_window_ms_spin.setSuffix(" ms")
        hf.addRow("时间窗口:", self.x_window_ms_spin)

        self.x_div_spin = QDoubleSpinBox(Content)
        self.x_div_spin.setRange(0.1, 100.0)
        self.x_div_spin.setDecimals(1)
        self.x_div_spin.setValue(10.0)
        self.x_div_spin.setSuffix(" 格")
        hf.addRow("格数:", self.x_div_spin)
        hg_layout.addLayout(hf)

        # ── input 1 子组（CH1 点数与时长）──
        hi1 = QGroupBox("input 1", Content)
        hi1.setStyleSheet("QGroupBox { color: #FFFF00; border: 1px solid #555; border-radius: 4px; margin-top: 8px; font-weight: bold; } QGroupBox::title { color: #FFFF00; subcontrol-origin: margin; left: 8px; padding: 0 4px; }")
        hi1f = QFormLayout(hi1)
        hi1f.setSpacing(3)
        lpts1 = QLabel("点数与时长:", Content)
        lpts1.setStyleSheet("color: #FFFF00;")
        self.input1_pts_dur_label = QLabel("--", Content)
        self.input1_pts_dur_label.setStyleSheet("color: #FFFF00;")
        hi1f.addRow(lpts1, self.input1_pts_dur_label)
        hg_layout.addWidget(hi1)

        # ── input 2 子组（CH2 点数与时长）──
        hi2 = QGroupBox("input 2", Content)
        hi2.setStyleSheet("QGroupBox { color: #00FFFF; border: 1px solid #555; border-radius: 4px; margin-top: 8px; font-weight: bold; } QGroupBox::title { color: #00FFFF; subcontrol-origin: margin; left: 8px; padding: 0 4px; }")
        hi2f = QFormLayout(hi2)
        hi2f.setSpacing(3)
        lpts2 = QLabel("点数与时长:", Content)
        lpts2.setStyleSheet("color: #00FFFF;")
        self.input2_pts_dur_label = QLabel("--", Content)
        self.input2_pts_dur_label.setStyleSheet("color: #00FFFF;")
        hi2f.addRow(lpts2, self.input2_pts_dur_label)
        hg_layout.addWidget(hi2)

        # 全局信息
        hf2 = QFormLayout()
        self.sampling_interval_label = QLabel("--", Content)
        hf2.addRow("采样间隔:", self.sampling_interval_label)
        hg_layout.addLayout(hf2)

        layout.addWidget(hg)

        # ── 其他选项 ──
        og = QGroupBox("其他选项", Content)
        of_ = QFormLayout(og)
        of_.setSpacing(3)

        self.fps_spin = QSpinBox(Content)
        self.fps_spin.setRange(1, 120)
        self.fps_spin.setValue(30)
        self.fps_spin.setSuffix(" fps")
        of_.addRow("帧率:", self.fps_spin)

        self.aa_check = QCheckBox("抗锯齿", Content)
        self.aa_check.setChecked(True)
        self.aa_check.setStyleSheet("color: #f0f0f0;")
        of_.addRow(self.aa_check)

        self.show_scale_check = QCheckBox("刻度绘制", Content)
        self.show_scale_check.setChecked(True)
        self.show_scale_check.setStyleSheet("color: #f0f0f0;")
        of_.addRow(self.show_scale_check)

        layout.addWidget(og)

        # ── 内存 ──
        mg = QGroupBox("内存", Content)
        mf = QFormLayout(mg)
        mf.setSpacing(3)
        self.memory_depth_spin = QSpinBox(Content)
        self.memory_depth_spin.setRange(100, 10_000_000)
        self.memory_depth_spin.setValue(10_000)
        self.memory_depth_spin.setSingleStep(1000)
        self.memory_depth_spin.setSuffix(" 点")
        mf.addRow("存储深度:", self.memory_depth_spin)
        layout.addWidget(mg)

    def retranslateUi(self, Content) -> None:
        """留空：文本在 setupUi 中已设置"""
        pass
