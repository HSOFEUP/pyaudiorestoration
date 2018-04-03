import soundfile as sf
import numpy as np
from time import time
import os
import fourier
import wow_detection
import resampling

def save(filename, data, piece=None):
	print("Writing trace data")
	piece_str  = ""
	if piece is not None:
		piece_str = "_"+str(piece)
	speedfilename = filename.rsplit('.', 1)[0]+piece_str+".spd"
	text_file = open(speedfilename, "wb")
	text_file.write(data.tobytes())
	text_file.close()

def write_speed(filename, speed_curve, piece=None):
	piece_str  = ""
	if piece is not None:
		piece_str = "_"+format(piece, '03d')
	#only for testing
	speedfilename = filename.rsplit('.', 1)[0]+piece_str+".npy"
	np.save(speedfilename, speed_curve, allow_pickle=True, fix_imports=True)

def read_speed(filename):
	#only for testing
	speedfilename = filename.rsplit('.', 1)[0]+".npy"
	return np.load(speedfilename)

def trace_all(filename, blocksize, overlap, fft_size, fft_overlap, hop, start= 16.7):
	start_time = time()
	#how many frames do we want?
	half = overlap//2
	quart = overlap//4
	#read in chunks for FFT
	soundob = sf.SoundFile(filename)
	sr = soundob.samplerate
	block_start = 0
	#just temporarily, in reality we will just store the end of the last file to crossfade
	alltimes = []
	allspeeds = []
	for i, block in enumerate(soundob.blocks( blocksize=blocksize*hop, overlap=overlap*hop)):
		# if i not in (0, 1):
			# continue
		print("Block from",block_start,"to",block_start+len(block)/sr)
		imdata = np.abs(fourier.stft(block, fft_size, hop, "hann"))
		
		#we can't do the start automatically
		#note: this is already accorded for in trace_peak
		if i == 0:
			t0 = start
			lag = 0
		else:
			#we only start at a good FFT, not influenced by cut artifacts
			t0 = fft_size/2/sr
			lag = fft_size//2 //hop
		print("start at",t0)
		times, freqs = wow_detection.trace_peak(imdata, fft_size, hop, sr, fL = 900, fU = 1100, t0 = t0, t1 = None, tolerance = 1, adaptation_mode="Average")
		if i == 0:
			times = times[:-half]
			freqs = freqs[:-half]
		else:
			times = times[half-lag:-half]
			freqs = freqs[half-lag:-half]
		alltimes.append( times )
		allspeeds.append( freqs )
		
		speed = np.stack((times, freqs), axis=1)
		write_speed(filename, speed, piece=i)
		block_start+= ((blocksize*hop - overlap*hop) / sr)

	dur = time() - start_time
	print("duration",dur)

	# import matplotlib.pyplot as plt
	# plt.figure()
	# plt.plot(alltimes[0], allspeeds[0], label="0", alpha=0.5)
	# #plt.plot(times, dbs, label="0", alpha=0.5)
	# #plt.plot(alltimes[1], allspeeds[1], label="1", alpha=0.5)
	# # plt.plot(alltimes[2], allspeeds[2], label="2", alpha=0.5)
	# # plt.plot(alltimes[3], allspeeds[3], label="3", alpha=0.5)
	# plt.xlabel('Speed')
	# plt.ylabel('Freg Hz')
	# plt.legend(frameon=True, framealpha=0.75)
	# plt.show()

def show_all(speedname, hi=1020, lo=948):
	dir = os.path.dirname(speedname)
	name = os.path.basename(speedname).rsplit('.', 1)[0]
	files = [os.path.join(dir,file) for file in os.listdir(dir) if name in file and file.endswith(".npy")]

	mins=[]
	maxs=[]
	
	speedcurves = []
	for file in files:
		speedcurve = np.load(file)
		speedcurves.append(speedcurve)
		#print(np.min(speedcurve[:,0]), np.max(speedcurve[:,0]))
		
		ma = np.max(speedcurve[:,1])
		mi = np.min(speedcurve[:,1])
		mins.append( mi)
		maxs.append(ma)
		if mi < lo:
			print("too low", file)
		if ma > hi:
			print("too high", file)
	import matplotlib.pyplot as plt
	plt.figure()
	plt.plot(mins, label="0", alpha=0.5)
	plt.plot(maxs, label="1", alpha=0.5)
	
	#maybe: set dropout freq to mean(freqs)
	#plt.plot(speedcurves[142][:,1], label="1", alpha=0.5)
	#plt.plot(times, dbs, label="0", alpha=0.5)
	# plt.plot(alltimes[1], allspeeds[1], label="1", alpha=0.5)
	# plt.plot(alltimes[2], allspeeds[2], label="2", alpha=0.5)
	# plt.plot(alltimes[3], allspeeds[3], label="3", alpha=0.5)
	plt.xlabel('Speed')
	plt.ylabel('Freg Hz')
	plt.legend(frameon=True, framealpha=0.75)
	plt.show()
	
	
def resample_all(speedname, filename, blocksize, overlap, hop):
	dir = os.path.dirname(speedname)
	name = os.path.basename(speedname).rsplit('.', 1)[0]
	files = [os.path.join(dir,file) for file in os.listdir(dir) if name in file and file.endswith(".npy")]
	batch_res(filename, blocksize, overlap, speed_curve_names=files, resampling_mode = "Linear")
	
	

def batch_res(filename, blocksize, overlap, speed_curve_names=None, resampling_mode = "Linear"):
	print('Analyzing ' + filename + '...')
	start_time = time()
	write_after=400000
	NT = 50
	#user/debugging info
	print(resampling_mode)
	#read the file
	soundob = sf.SoundFile(filename)
	sr = soundob.samplerate
	block_start = 0
	#just temporarily, in reality we will just store the end of the last file to crossfade
	alltimes = []
	allspeeds = []
	outfilename = filename.rsplit('.', 1)[0]+'_cloned.wav'
	with sf.SoundFile(outfilename, 'w', sr, 1, subtype='FLOAT') as outfile:
		in_len = 0
		for i, in_block in enumerate(soundob.blocks( blocksize=blocksize*hop, overlap=overlap*hop)):
			#if i not in (0, 1,2,3):
			#	continue
			print(i, len(in_block))
			speed_curve = np.load(speed_curve_names[i])
			times = speed_curve[:,0]
			print("times:",times[0],times[len(times)-1])
			#note: this expects a a linscale speed curve centered around 1 (= no speed change)
			speeds = speed_curve[:,1]/1000
			periods = np.diff(times)*sr
			print("speeds",len(speeds))
			
			#just overwrite if needed
			#if in_len != len(in_block):
			in_len = len(in_block)
			samples_in2 = np.arange(0, in_len)
				
			offsets_speeds = []
			#offset = 0
			offset = int(times[0]*sr)
			err = 0
			temp_offset = 0
			temp_pos = []
			for i2 in range(0, len(speeds)-1):
				#save a new block for interpolation
				if len(temp_pos)* periods[i2] > write_after:
					offsets_speeds.append( ( offset, np.concatenate(temp_pos) ) )
					offset += temp_offset
					temp_offset = 0
					temp_pos = []
				#we want to know how many samples there are in this section, so get the period (should be the same for all sections)
				mean_speed = ( (speeds[i2]+speeds[i2+1])/ 2 )
				#the desired number of samples in this block - this is clearly correct
				n = periods[i2]*mean_speed
				
				inerr = n + err
				n = round(inerr)
				err =  inerr-n
				
				#4.1 s for interp(arange)
				#4.5 s for interp(generator)
				#5.6 s for np.linspace(speeds[i], speeds[i+1], n)
				#6.5 s for intrp(linspace)
				#block_speeds = np.interp([i for i in range(0,int(n)+1)], (0, n),(speeds[i], speeds[i+1])  )
				block_speeds = np.interp(np.arange(n), (0, n-1), (speeds[i2], speeds[i2+1]) )
				positions = np.cumsum(1/block_speeds)
				
				temp_pos.append( positions +  temp_offset)
				temp_offset+=positions[-1]

			if temp_pos: offsets_speeds.append( (offset, np.concatenate(temp_pos) ) )
			num_blocks = len(offsets_speeds)

			for offset, positions in offsets_speeds:
				outfile.write( np.interp(positions, samples_in2-int(offset), in_block) )

	dur = time() - start_time
	print("duration",dur)

#settings...
fft_size=512
fft_overlap=16
hop=512//16
overlap=100
blocksize=100000
speedname = "C:/Users/arnfi/Desktop/nasa/A11_T876_HR1L_CH1.wav"
filename = "C:/Users/arnfi/Desktop/nasa/A11_T876_HR1L_CH2.wav"
trace_all(speedname, blocksize, overlap, fft_size, fft_overlap, hop, start= 16.7)
#show_all(speedname, hi=1020, lo=948)
#resample_all(speedname, filename, blocksize, overlap, hop)