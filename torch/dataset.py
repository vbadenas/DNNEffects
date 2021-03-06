import logging
from torch.utils.data import Dataset
import torch
import pandas as pd
import soundfile as sf
import numpy as np
from utils import timer
import math


class LstDataset(Dataset):
    def __init__(self, parameters, lst_path):
        super(LstDataset, self).__init__()
        self.parameters = parameters
        self.lst_data = self.load_lst(lst_path)
        self.load_audio_data()
        self.compute_frame_list()

    @staticmethod
    def load_lst(lst_path):
        if not lst_path.exists():
            raise OSError("lst file not found")
        return pd.read_csv(lst_path, sep='\t')

    def load_audio_data(self):
        self.source_audio_files, load_time = self.load_audio_files(label='source', timer=timer)
        logging.info(f"source audio files have been loaded in {load_time:.2f}s")
        self.target_audio_files, load_time = self.load_audio_files(label='target', timer=timer)
        logging.info(f"target audio files have been loaded in {load_time:.2f}s")

    def compute_frame_list(self):
        self.compute_frame_list_from_audio_files(self.source_audio_files)

    def compute_frame_list_from_audio_files(self, audio_files_array):
        self.frames = []
        silence_threshold = 1e-8
        for audioIdx, audiofile in enumerate(audio_files_array):
            for frameIdx, frame in enumerate(audiofile):
                if np.sum(abs(frame)**2)/len(frame) > silence_threshold:
                    self.frames.append({"audio_idx": audioIdx, "frame_idx": frameIdx})
        logging.info(f"{len(self.frames)} have been computed")

    @timer(print_=False)
    def load_audio_files(self, label, timer=None):
        return [AudioFile(source_file, self.parameters.frame_length) for source_file in self.lst_data[label]]

    def __len__(self):
        return len(self.frames)

    def __getitem__(self, idx):
        audio_idx, frame_idx = self.frames[idx]['audio_idx'], self.frames[idx]['frame_idx']
        source_frame = self.source_audio_files[audio_idx].get_frame(frame_idx)
        target_frame = self.target_audio_files[audio_idx].get_frame(frame_idx)
        return torch.Tensor(source_frame).unsqueeze(1), torch.Tensor(target_frame).unsqueeze(1)


class DatasetFromDisk(LstDataset):
    def __init__(self, parameters, lst_path):
        super(LstDataset, self).__init__()
        self.parameters = parameters
        self.lst_data = self.load_lst(lst_path)
        self.load_audio_data()
        self.compute_frame_list()
        self.delete_audio_data()

    def delete_audio_data(self):
        del self.source_audio_files, self.target_audio_files

    def __getitem__(self, idx):
        audio_idx, frame_idx = self.frames[idx]['audio_idx'], self.frames[idx]['frame_idx']
        source_file = self.lst_data['source'][audio_idx]
        source_frame = AudioFile(source_file, self.parameters.frame_length).get_frame(frame_idx)
        target_file = self.lst_data['target'][audio_idx]
        target_frame = AudioFile(target_file, self.parameters.frame_length).get_frame(frame_idx)
        return torch.Tensor(source_frame).unsqueeze(1), torch.Tensor(target_frame).unsqueeze(1)


class AudioFile:
    def __init__(self, audiofile_path, frame_length):
        self.frame_counter = 0
        self.audiofile_path = audiofile_path
        self.frame_length = frame_length
        self.load_audio_data()

    def load_audio_data(self):
        self.audio_data, self.sample_rate = sf.read(self.audiofile_path)
        self.audio_length = len(self.audio_data)

    def __len__(self):
        return int(self.audio_length / self.frame_length)

    def has_next_frame(self):
        return self.frame_counter <= len(self)

    def get_next_frame(self):
        start_index = self.frame_counter * self.frame_length
        end_index = start_index + self.frame_length
        current_frame = self.audio_data[start_index:end_index]
        self.frame_counter += 1
        return current_frame

    def get_frame(self, frame_idx):
        start_index = frame_idx * self.frame_length
        end_index = start_index + self.frame_length
        return self.audio_data[start_index:end_index]

    def zero_pad(self):
        remaining = self.audio_length % self.frame_length
        if remaining == 0:
            return
        zero_pad = np.zeros(self.frame_length - remaining)
        self.audio_data = np.concatenate((self.audio_data, zero_pad))
        self.audio_length = len(self.audio_data)

    def __iter__(self):
        return self

    def __next__(self):
        if self.frame_counter >= len(self):
            self.frame_counter = 0
            raise StopIteration
        else:
            frame = self.get_frame(self.frame_counter)
            self.frame_counter += 1
            return frame
