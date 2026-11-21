# Local helpers. build.sh builds out/bb-probe and out/gpu/libbbgpu.so; sotc.py starts them. The game
# dump is ../CUSA08809 or SOTC_GAME_DIR (see sotc.py).

.PHONY: build play

build:
	bash build.sh

play:
	bash run.sh
