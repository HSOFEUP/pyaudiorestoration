import os
import numpy as np
import soundfile as sf
from vispy import scene, color
from PyQt5 import QtGui, QtCore, QtWidgets

#custom modules
from util import vispy_ext, fourier, spectrum, resampling, wow_detection, qt_theme, snd

myFont=QtGui.QFont()
myFont.setBold(True)

def grid(buttons):
	qgrid = QtWidgets.QGridLayout()
	qgrid.setHorizontalSpacing(3)
	qgrid.setVerticalSpacing(0)
	for i, line in enumerate(buttons):
		for j, element in enumerate(line):
			#we want to stretch that one
			if 1 == len(line):
				qgrid.addWidget(line[j], i, j, 1, 2)
			else:
				qgrid.addWidget(line[j], i, j)
	for i in range(2):
		qgrid.setColumnStretch(i, 1)
	return qgrid
	
def vbox(self, grid):
	vbox = QtWidgets.QVBoxLayout(self)
	vbox.addLayout(grid)
	vbox.addStretch(1.0)
	vbox.setSpacing(0)
	vbox.setContentsMargins(0,0,0,0)
	
class DisplayWidget(QtWidgets.QWidget):
	def __init__(self, canvas):
		QtWidgets.QWidget.__init__(self,)
		self.canvas = canvas
		
		display_l = QtWidgets.QLabel("Display")
		display_l.setFont(myFont)
		
		fft_l = QtWidgets.QLabel("FFT Size")
		self.fft_c = QtWidgets.QComboBox(self)
		self.fft_c.addItems(("64", "128", "256", "512", "1024", "2048", "4096", "8192", "16384", "32768", "65536", "131072"))
		self.fft_c.setToolTip("This determines the frequency resolution.")
		self.fft_c.setCurrentIndex(5)
		
		overlap_l = QtWidgets.QLabel("FFT Overlap")
		self.overlap_c = QtWidgets.QComboBox(self)
		self.overlap_c.addItems(("1", "2", "4", "8", "16", "32"))
		self.overlap_c.setToolTip("Increase to improve temporal resolution.")
		self.overlap_c.setCurrentIndex(2)
		
		show_l = QtWidgets.QLabel("Show")
		self.show_c = QtWidgets.QComboBox(self)
		self.show_c.addItems(("Both","Traces","Regressions"))
		
		cmap_l = QtWidgets.QLabel("Colors")
		self.cmap_c = QtWidgets.QComboBox(self)
		self.cmap_c.addItems(sorted(color.colormap.get_colormaps().keys()))
		self.cmap_c.setCurrentText("viridis")
	
		buttons = ((display_l,), (fft_l, self.fft_c), (overlap_l, self.overlap_c), (show_l, self.show_c), (cmap_l,self.cmap_c))
		vbox(self, grid(buttons))
		
		#only connect in the end
		self.fft_c.currentIndexChanged.connect(self.update_fft_settings)
		self.overlap_c.currentIndexChanged.connect(self.update_fft_settings)
		self.show_c.currentIndexChanged.connect(self.update_show_settings)
		self.cmap_c.currentIndexChanged.connect(self.update_cmap)

	@property
	def fft_size(self): return int(self.fft_c.currentText())
	
	@property
	def fft_overlap(self): return int(self.overlap_c.currentText())
	
	def update_fft_settings(self,):
		self.canvas.set_file_or_fft_settings(self.canvas.filenames,
											 fft_size = self.fft_size,
											 fft_overlap = self.fft_overlap)
		# also force a cmap update here
		self.update_cmap()
		
	def update_show_settings(self):
		show = self.show_c.currentText()
		if show == "Traces":
			self.canvas.show_regs = False
			self.canvas.show_lines = True
			self.canvas.master_speed.show()
			for trace in self.canvas.lines:
				trace.show()
			self.canvas.master_reg_speed.hide()
			for reg in self.canvas.regs:
				reg.hide()
		elif show == "Regressions":
			self.canvas.show_regs = True
			self.canvas.show_lines = False
			self.canvas.master_speed.hide()
			for trace in self.canvas.lines:
				trace.hide()
			self.canvas.master_reg_speed.show()
			for reg in self.canvas.regs:
				reg.show()
		elif show == "Both":
			self.canvas.show_regs = True
			self.canvas.show_lines = True
			self.canvas.master_speed.show()
			for trace in self.canvas.lines:
				trace.show()
			self.canvas.master_reg_speed.show()
			for reg in self.canvas.regs:
				reg.show()
				
	def update_cmap(self):
		self.canvas.set_colormap(self.cmap_c.currentText())	

class TracingWidget(QtWidgets.QWidget):
	def __init__(self, canvas):
		QtWidgets.QWidget.__init__(self,)
		self.canvas = canvas
		tracing_l = QtWidgets.QLabel("\nTracing")
		tracing_l.setFont(myFont)
		trace_l = QtWidgets.QLabel("Mode")
		self.trace_c = QtWidgets.QComboBox(self)
		self.trace_c.addItems(("Center of Gravity","Peak","Correlation","Freehand Draw", "Sine Regression"))
		
		rpm_l = QtWidgets.QLabel("Source RPM")
		self.rpm_c = QtWidgets.QComboBox(self)
		self.rpm_c.setEditable(True)
		self.rpm_c.addItems(("Unknown","33.333","45","78"))
		self.rpm_c.setToolTip("This helps avoid bad values in the sine regression. \nIf you don't know the source, measure the duration of one wow cycle. \nRPM = 60/cycle length")
		
		phase_l = QtWidgets.QLabel("Phase Offset")
		self.phase_s = QtWidgets.QSpinBox()
		self.phase_s.setRange(-20, 20)
		self.phase_s.setSingleStep(1)
		self.phase_s.setValue(0)
		self.phase_s.valueChanged.connect(self.update_phase_offset)
		self.phase_s.setToolTip("Adjust the phase of the selected sine regression to match the surrounding regions.")
		
		tolerance_l = QtWidgets.QLabel("Tolerance")
		self.tolerance_s = QtWidgets.QDoubleSpinBox()
		self.tolerance_s.setRange(.01, 5)
		self.tolerance_s.setSingleStep(.05)
		self.tolerance_s.setValue(.1)
		self.tolerance_s.setToolTip("Intervall to consider in the trace, in semitones.")
		
		adapt_l = QtWidgets.QLabel("Adaptation")
		self.adapt_c = QtWidgets.QComboBox(self)
		self.adapt_c.addItems(("Average", "Linear", "Constant", "None"))
		self.adapt_c.setToolTip("Used to predict the next frequencies when tracing.")
		
		self.autoalign_b = QtWidgets.QCheckBox("Auto-Align")
		self.autoalign_b.setChecked(True)
		self.autoalign_b.setToolTip("Should new traces be aligned with existing ones?")
		
		buttons = ((tracing_l,), (trace_l, self.trace_c), (adapt_l, self.adapt_c), (rpm_l,self.rpm_c), (phase_l, self.phase_s), (tolerance_l, self.tolerance_s), (self.autoalign_b, ))
		vbox(self, grid(buttons))

	@property
	def mode(self): return self.trace_c.currentText()
	
	@property
	def tolerance(self): return self.tolerance_s.value()
	
	@property
	def adapt(self): return self.adapt_c.currentText()
	
	@property
	def auto_align(self): return self.autoalign_b.isChecked()
	
	@property
	def rpm(self): return self.rpm_c.currentText()
	
	def update_phase_offset(self):
		v = self.phase_s.value()
		for reg in self.canvas.regs:
			reg.update_phase(v)
		self.canvas.master_reg_speed.update()
	
class ResamplingWidget(QtWidgets.QWidget):
	def __init__(self, ):
		QtWidgets.QWidget.__init__(self,)
		
		resampling_l = QtWidgets.QLabel("\nResampling")
		resampling_l.setFont(myFont)
		mode_l = QtWidgets.QLabel("Mode")
		self.mode_c = QtWidgets.QComboBox(self)
		self.mode_c.addItems(("Linear", "Sinc"))
		self.mode_c.currentIndexChanged.connect(self.toggle_resampling_quality)
		self.sinc_quality_l = QtWidgets.QLabel("Quality")
		self.sinc_quality_s = QtWidgets.QSpinBox()
		self.sinc_quality_s.setRange(1, 100)
		self.sinc_quality_s.setSingleStep(1)
		self.sinc_quality_s.setValue(50)
		self.sinc_quality_s.setToolTip("Number of input samples that contribute to each output sample.\nMore samples = more quality, but slower. Only for sinc mode.")
		self.toggle_resampling_quality()
		
		
		self.mygroupbox = QtWidgets.QGroupBox('Channels')
		self.mygroupbox.setToolTip("Only selected channels will be resampled.")
		self.channel_layout = QtWidgets.QVBoxLayout()
		self.channel_layout.setSpacing(0)
		self.mygroupbox.setLayout(self.channel_layout)
		self.scroll = QtWidgets.QScrollArea()
		self.scroll.setWidget(self.mygroupbox)
		self.scroll.setWidgetResizable(True)
		self.channel_checkboxes = [ ]
		
		self.progressBar = QtWidgets.QProgressBar(self)
		self.progressBar.setRange(0,100)
		self.progressBar.setAlignment(QtCore.Qt.AlignCenter)
		
		buttons = ((resampling_l,), (mode_l, self.mode_c,), (self.sinc_quality_l, self.sinc_quality_s), (self.scroll,), (self.progressBar,))
		vbox(self, grid(buttons))
		
	def toggle_resampling_quality(self):
		b = (self.mode_c.currentText() == "Sinc")
		self.sinc_quality_l.setVisible(b)
		self.sinc_quality_s.setVisible(b)
		
	def refill(self, num_channels):
		for channel in self.channel_checkboxes:
			self.channel_layout.removeWidget(channel)
			channel.deleteLater()
		self.channel_checkboxes = []
		
		#fill the channel UI
		channel_names = ("Front Left", "Front Right", "Center", "LFE", "Back Left", "Back Right")
		for i in range(0, num_channels):
			name = channel_names[i] if i < 6 else str(i)
			self.channel_checkboxes.append(QtWidgets.QCheckBox(name))
			# set the startup option to just resample channel 0
			self.channel_checkboxes[-1].setChecked(True if i == 0 else False)
			self.channel_layout.addWidget( self.channel_checkboxes[-1] )
			
	def onProgress(self, i):
		self.progressBar.setValue(i)

	@property
	def channels(self, ): return [i for i, channel in enumerate(self.channel_checkboxes) if channel.isChecked()]
	
	@property
	def sinc_quality(self, ): return self.sinc_quality_s.value()
	
	@property
	def mode(self, ): return self.mode_c.currentText()
	
class InspectorWidget(QtWidgets.QLabel):
	def __init__(self, ):
		QtWidgets.QLabel.__init__(self, )
		self.def_text = "\n        -.- Hz\n-:--:--:--- h:m:s:ms"
		myFont2=QtGui.QFont("Monospace")
		myFont2.setStyleHint(QtGui.QFont.TypeWriter)
		self.setFont(myFont2)
		
	def update_text(self, click, sr):
		self.setText(self.def_text)
		if click is not None:
			t, f = click[0:2]
			if t >= 0 and  sr/2 > f >= 0:
				m, s = divmod(t, 60)
				s, ms = divmod(s*1000, 1000)
				h, m = divmod(m, 60)
				self.setText("\n   % 8.1f Hz\n%d:%02d:%02d:%03d h:m:s:ms" % (f, h, m, s, ms))
				

class MainWindow(QtWidgets.QMainWindow):

	def __init__(self, name, object_widget, canvas_widget):
		QtWidgets.QMainWindow.__init__(self)		
		
		self.resize(720, 400)
		self.setWindowTitle(name)
		try:
			base_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
			self.setWindowIcon(QtGui.QIcon(os.path.join(base_dir,'icons/'+name+'.png')))
		except: pass
		
		self.setAcceptDrops(True)

		self.canvas = canvas_widget()
		self.canvas.create_native()
		self.canvas.native.setParent(self)
		self.props = object_widget(parent=self)
		self.canvas.props = self.props

		splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
		splitter.addWidget(self.canvas.native)
		splitter.addWidget(self.props)
		self.setCentralWidget(splitter)
		
	def add_to_menu(self, button_data):
		for submenu, name, func, shortcut in button_data:
			button = QtWidgets.QAction(name, self)
			button.triggered.connect(func)
			if shortcut: button.setShortcut(shortcut)
			submenu.addAction(button)
		
	def dragEnterEvent(self, event):
		if event.mimeData().hasUrls:
			event.accept()
		else:
			event.ignore()

	def dragMoveEvent(self, event):
		if event.mimeData().hasUrls:
			event.setDropAction(QtCore.Qt.CopyAction)
			event.accept()
		else:
			event.ignore()

	def dropEvent(self, event):
		if event.mimeData().hasUrls:
			event.setDropAction(QtCore.Qt.CopyAction)
			event.accept()
			for url in event.mimeData().urls():
				self.props.load_audio( str(url.toLocalFile()) )
				return
		else:
			event.ignore()