# Copyright The PyTorch Lightning team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import os
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock

import pytest
import torch

from pytorch_lightning import Trainer
from pytorch_lightning.callbacks import ModelCheckpoint
from pytorch_lightning.demos.boring_classes import BoringModel
from pytorch_lightning.plugins.io.torch_plugin import TorchCheckpointIO
from pytorch_lightning.strategies import SingleDeviceStrategy
from pytorch_lightning.utilities.exceptions import MisconfigurationException
from pytorch_lightning.utilities.types import _PATH


class CustomCheckpointIO(TorchCheckpointIO):
    def load_checkpoint(self, path: _PATH, storage_options: Optional[Any] = None) -> Dict[str, Any]:
        return torch.load(path)

    def remove_checkpoint(self, path: _PATH) -> None:
        os.remove(path)


def test_checkpoint_plugin_called(tmpdir):
    """Ensure that the custom checkpoint IO plugin and torch checkpoint IO plugin is called when saving/loading."""
    checkpoint_plugin = CustomCheckpointIO()
    checkpoint_plugin = MagicMock(wraps=checkpoint_plugin, spec=CustomCheckpointIO)

    ck = ModelCheckpoint(dirpath=tmpdir, save_last=True)

    model = BoringModel()
    trainer = Trainer(
        default_root_dir=tmpdir,
        strategy=SingleDeviceStrategy("cpu", checkpoint_io=checkpoint_plugin),
        callbacks=ck,
        max_epochs=2,
        limit_train_batches=1,
        limit_val_batches=0,
        limit_test_batches=1,
    )
    trainer.fit(model)

    ckpt_files = {fn.name for fn in Path(tmpdir).glob("*.ckpt")}
    assert ckpt_files == {"epoch=1-step=2.ckpt", "last.ckpt"}
    assert trainer.checkpoint_callback.best_model_path == tmpdir / "epoch=1-step=2.ckpt"
    assert trainer.checkpoint_callback.last_model_path == tmpdir / "last.ckpt"
    assert checkpoint_plugin.save_checkpoint.call_count == 4
    assert checkpoint_plugin.remove_checkpoint.call_count == 1

    trainer.test(model, ckpt_path=ck.last_model_path)
    checkpoint_plugin.load_checkpoint.assert_called_with(tmpdir / "last.ckpt")

    checkpoint_plugin.reset_mock()
    ck = ModelCheckpoint(dirpath=tmpdir, save_last=True)

    model = BoringModel()
    trainer = Trainer(
        default_root_dir=tmpdir,
        strategy=SingleDeviceStrategy("cpu"),
        plugins=[checkpoint_plugin],
        callbacks=ck,
        max_epochs=2,
        limit_train_batches=1,
        limit_val_batches=0,
        limit_test_batches=1,
    )
    trainer.fit(model)

    ckpt_files = {fn.name for fn in Path(tmpdir).glob("*.ckpt")}
    assert ckpt_files == {"epoch=1-step=2.ckpt", "last.ckpt", "epoch=1-step=2-v1.ckpt", "last-v1.ckpt"}
    assert trainer.checkpoint_callback.best_model_path == tmpdir / "epoch=1-step=2-v1.ckpt"
    assert trainer.checkpoint_callback.last_model_path == tmpdir / "last-v1.ckpt"
    assert checkpoint_plugin.save_checkpoint.call_count == 4
    assert checkpoint_plugin.remove_checkpoint.call_count == 1

    trainer.test(model, ckpt_path=ck.last_model_path)
    checkpoint_plugin.load_checkpoint.assert_called_once()
    checkpoint_plugin.load_checkpoint.assert_called_with(tmpdir / "last-v1.ckpt")


def test_checkpoint_plugin_called_async(tmpdir):
    """Ensure that the custom checkpoint IO plugin and torch checkpoint IO plugin is called when async saving and
    loading."""
    checkpoint_plugin = CustomCheckpointIO(save_async=True, num_threads=2)
    checkpoint_plugin = MagicMock(wraps=checkpoint_plugin, spec=CustomCheckpointIO)

    ck = ModelCheckpoint(dirpath=tmpdir, save_top_k=-1)

    model = BoringModel()
    trainer = Trainer(
        default_root_dir=tmpdir,
        strategy=SingleDeviceStrategy("cpu", checkpoint_io=checkpoint_plugin),
        callbacks=ck,
        max_epochs=2,
        limit_train_batches=1,
        limit_val_batches=0,
    )
    trainer.fit(model)

    ckpt_files = {fn.name for fn in Path(tmpdir).glob("*.ckpt")}
    assert ckpt_files == {"epoch=0-step=1.ckpt", "epoch=1-step=2.ckpt"}
    assert checkpoint_plugin.save_checkpoint.call_count == 2
    assert checkpoint_plugin.remove_checkpoint.call_count == 0


def test_invalid_configuration_with_async():
    with pytest.raises(MisconfigurationException, match="not possible with `num_threads=0`"):
        TorchCheckpointIO(save_async=True, num_threads=0)
