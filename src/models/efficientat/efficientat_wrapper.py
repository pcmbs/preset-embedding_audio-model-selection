# pylint: disable=E1101
"""
Wrapper class around EfficientAT [1] models for integration into the current pipeline.

stripped down version of the EfficientAT repo available at
https://github.com/fschmid56/EfficientAT_HEAR/tree/main 

[1] Schmid, F., Koutini, K., & Widmer, G. (2022). 
Efficient Large-scale Audio Tagging via Transformer-to-CNN Knowledge Distillation.
http://arxiv.org/abs/2211.04772


"""
import os
from dotenv import load_dotenv
import torch
from torch import nn

from . import hear_mn


load_dotenv()  # take environment variables from .env for checkpoints folder
torch.hub.set_dir(os.environ["PROJECT_ROOT"])  # path to download/load checkpoints


# Mono audio is sampled at 32 kHz and STFT is computed using 25 ms windows and a hop size of 10 ms.
# Log mel spectrograms with 128 frequency bands are computed and serve as input to the models.

##### Model terminology

# Clf 1 denotes the features resulting from global pooling,
# Clf 2 is the embedding from the penultimate linear layer and
# Clf 3 are the logits predicted for the 527 classes of AudioSet
# all_se denotes the output of all SE bottleneck layers
# b{i} denotes the features extracted from the i-th block using global avg pooling
# all_b denotes the features extracted from blocks b2, b11, b13, b15 using global avg pooling


# Possible candidates
# mn04_all_b_mel_avgs
# mn10_all_b_mel_avgs
# mn10_all_b_mel_avgs_mels256
# mn20_all_b_mel_avgs
# mn30_all_b_mel_avgs
# mn40_all_b_mel_avgs


class EfficientATWrapper(nn.Module):
    def __init__(self, model_name: str = "mn10_all_b_mel_avgs") -> None:
        super().__init__()
        self._module = getattr(hear_mn, model_name)
        self.model = self._module.load_model()
        self.model_name = model_name

    @property
    def segment(self) -> None:
        # should be 10 but seems to truncate results to original input length
        return None

    @property
    def sample_rate(self) -> int:
        return 32_000

    @property
    def channels(self) -> int:
        return 1

    @property
    def name(self) -> str:
        return self.model_name

    def forward(self, audio: torch.Tensor) -> torch.Tensor:
        """
        Forward pass.
        audio (torch.Tensor): mono input sounds @32khz of shape (n_sounds, n_channels=1, n_samples) in the range [-1, 1]
        """
        # passt requires mono input audio of shape (n_sounds, n_samples)
        audio = audio.squeeze(-2)
        embeddings, _ = self._module.get_timestamp_embeddings(audio, self.model)
        return embeddings.swapdims_(-1, -2)  # swap time and channel dims


if __name__ == "__main__":
    encoder = EfficientATWrapper(model_name="mn10_all_b")
    audio = torch.empty((1, 1, 32_000 * 1)).uniform_(-1, 1)
    embeddings = encoder(audio)
    print(f"timestamp embeddings shape: {embeddings.shape}")
