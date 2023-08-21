"""
Wrapper class around AudioMAE [1] for integration into the current pipeline.

Github Repo: https://github.com/facebookresearch/AudioMAE/tree/main

[1] @inproceedings{huang2022amae,
  title = {Masked Autoencoders that Listen},
  author = {Huang, Po-Yao and Xu, Hu and Li, Juncheng and Baevski, Alexei and Auli, Michael and Galuba, Wojciech and Metze, Florian and Feichtenhofer, Christoph}
  booktitle = {NeurIPS},
  year = {2022}
}
"""
import os
from pathlib import Path

import numpy as np
import torch
import torchaudio
from dotenv import load_dotenv
from torch import nn

from . import mae_vit_base_patch16

load_dotenv()  # take environment variables from .env for checkpoints folder
# path to download/load checkpoints
CKPT_FOLDER = Path(os.environ["PROJECT_ROOT"]) / "checkpoints"
torch.hub.set_dir(CKPT_FOLDER)

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# Adapted from
# https://github.com/facebookresearch/AudioMAE/blob/main/demo/aud_mae_visualize.ipynb


class AudioMAEWrapper(nn.Module):
    def __init__(self, ckpt_name: str = "as-2M_pt") -> None:
        super().__init__()
        if ckpt_name == "as-2M_pt+ft":
            ckpt_id = "18EsFOyZYvBYHkJ7_n7JFFWbj6crz01gq"
        elif ckpt_name == "as-2M_pt":
            ckpt_id = "1ni_DV4dRf7GxM8k-Eirx71WP9Gg89wwu"
        else:
            raise ValueError(
                f"Invalid checkpoint name: {ckpt_name}. Must be one of ['as_2M_pt+ft', 'as_2M_pt']"
            )

        self.ckpt_name = ckpt_name
        ckpt_path = CKPT_FOLDER / f"audio-mae_{ckpt_name}.pth"

        # download and load weights from google drive link
        if not ckpt_path.exists():
            torch.hub.download_url_to_file(
                url=f"https://drive.google.com/uc?export=download&confirm=s5vl&id={ckpt_id}",
                dst=ckpt_path,
            )
        checkpoint = torch.load(
            ckpt_path,
            map_location=DEVICE,
        )

        # build model
        self.model = mae_vit_base_patch16(
            in_chans=1, audio_exp=True, img_size=(1024, 128)
        )
        miss, _ = self.model.load_state_dict(checkpoint["model"], strict=False)
        print(f"Missing weights from checkpoint: {miss}")

        # stats for mel spectrogram normalization
        self.norm_mean = -4.2677393
        self.norm_std = 4.5689974

    @property
    def segment(self) -> None:
        return None  # should be 10, to check

    @property
    def sample_rate(self) -> int:
        return 44_100

    @property
    def channels(self) -> int:
        return 1

    @property
    def name(self) -> str:
        return f"audio-mae_{self.ckpt_name}"

    def forward(self, audio: torch.Tensor) -> torch.Tensor:
        """
        Forward pass.
        audio (torch.Tensor): mono input sounds @44,1khz of shape (n_sounds, n_channels=1, n_samples) in the range [-1, 1]

        Returns:
            torch.Tensor: audio embeddings of shape (n_sounds, embed_size=768, num_patches=513)
        """
        # kaldi fbanks can only be computed for a single audio sample at a time
        fbanks_batch = torch.stack([self._wav2fbank(sample) for sample in audio], dim=0)
        fbanks_batch.unsqueeze_(dim=1)  # add the channel dimension
        embeddings = self.model.forward_encoder_no_mask(fbanks_batch)
        return embeddings.transpose(-1, -2)

    def _wav2fbank(self, audio: torch.Tensor) -> torch.Tensor:
        TARGET_LEN = 1024
        MELBINS = 128

        audio = audio - audio.mean()

        # 498 128
        fbank = torchaudio.compliance.kaldi.fbank(
            audio,
            htk_compat=True,
            sample_frequency=self.sample_rate,
            use_energy=False,
            window_type="hanning",
            num_mel_bins=MELBINS,
            dither=0.0,
            frame_shift=10,
        )
        # AudioSet: 1024 (16K sr)
        # ESC: 512 (8K sr)
        n_frames = fbank.shape[0]
        p = TARGET_LEN - n_frames
        # cut and pad
        if p > 0:
            m = torch.nn.ZeroPad2d((0, 0, 0, p))
            fbank = m(fbank)
        elif p < 0:
            fbank = fbank[0:TARGET_LEN, :]

        fbank = (fbank - self.norm_mean) / (self.norm_std * 2)

        return fbank
