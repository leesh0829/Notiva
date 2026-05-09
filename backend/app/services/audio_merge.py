from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


class AudioMergeError(RuntimeError):
    pass


def _ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise AudioMergeError(
            "ffmpeg 실행 파일을 찾을 수 없습니다. backend 의존성을 다시 설치해주세요 (imageio-ffmpeg)."
        ) from exc
    return imageio_ffmpeg.get_ffmpeg_exe()


def _decode_to_wav(ffmpeg_exe: str, input_path: Path, output_path: Path) -> None:
    """Decode a single (possibly truncated) audio file to 16kHz mono PCM WAV.

    ffmpeg is far more lenient than browser decodeAudioData: it can recover
    truncated WebM containers (e.g., browser crash mid-recording) by reading
    valid clusters and ignoring the missing terminator.
    """
    process = subprocess.run(
        [
            ffmpeg_exe,
            "-hide_banner",
            "-loglevel", "warning",
            "-err_detect", "ignore_err",
            "-fflags", "+genpts+igndts",
            "-i", str(input_path),
            "-vn",
            "-ac", "1",
            "-ar", "16000",
            "-c:a", "pcm_s16le",
            "-y",
            str(output_path),
        ],
        capture_output=True,
        text=True,
    )
    if process.returncode != 0 or not output_path.exists() or output_path.stat().st_size == 0:
        stderr = (process.stderr or "").strip()
        raise AudioMergeError(
            f"오디오 디코딩 실패: {input_path.name} — {stderr[-500:] if stderr else 'ffmpeg returned empty output'}"
        )


def merge_audio_files_to_wav(files: list[tuple[str, bytes]]) -> bytes:
    """Decode each file with ffmpeg, concat in order, return merged WAV bytes."""
    if not files:
        raise AudioMergeError("병합할 오디오 파일이 없습니다.")

    ffmpeg_exe = _ffmpeg_exe()

    with tempfile.TemporaryDirectory(prefix="notiva-merge-") as tmp:
        tmpdir = Path(tmp)
        wav_paths: list[Path] = []
        for index, (filename, payload) in enumerate(files):
            if not payload:
                raise AudioMergeError(f"빈 파일: {filename or f'#{index + 1}'}")
            suffix = Path(filename or f"input-{index}.bin").suffix or ".bin"
            input_path = tmpdir / f"input-{index}{suffix}"
            input_path.write_bytes(payload)
            output_path = tmpdir / f"decoded-{index}.wav"
            _decode_to_wav(ffmpeg_exe, input_path, output_path)
            wav_paths.append(output_path)

        if len(wav_paths) == 1:
            return wav_paths[0].read_bytes()

        list_path = tmpdir / "concat.txt"
        with list_path.open("w", encoding="utf-8") as handle:
            for wav in wav_paths:
                escaped = str(wav).replace("'", "'\\''")
                handle.write(f"file '{escaped}'\n")

        merged_path = tmpdir / "merged.wav"
        process = subprocess.run(
            [
                ffmpeg_exe,
                "-hide_banner",
                "-loglevel", "warning",
                "-f", "concat",
                "-safe", "0",
                "-i", str(list_path),
                "-c", "copy",
                "-y",
                str(merged_path),
            ],
            capture_output=True,
            text=True,
        )
        if process.returncode != 0 or not merged_path.exists() or merged_path.stat().st_size == 0:
            stderr = (process.stderr or "").strip()
            raise AudioMergeError(
                f"오디오 병합 실패: {stderr[-500:] if stderr else 'ffmpeg concat returned empty output'}"
            )

        return merged_path.read_bytes()
