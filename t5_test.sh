#!/bin/sh
MODEL=$1
DATA_SIZE=$2
OUTPUT_DIR="./models/${MODEL}_${DATA_SIZE}"
# OUTPUT_DIR="./models/test"

CUDA_VISIBLE_DEVICES=0 python ./scripts/run_experiment_t5.py \
--model_type t5 \
--model_name_or_path $MODEL \
--data_size $DATA_SIZE \
--task_name winogrande_ps \
--do_eval \
--do_lower_case \
--data_dir ./data \
--max_seq_length 100 \
--per_gpu_eval_batch_size 8 \
--per_gpu_train_batch_size 1 \
--gradient_accumulation_steps 1 \
--learning_rate 1e-3 \
--num_train_epochs 10 \
--output_dir $OUTPUT_DIR \
--do_train \
--logging_steps 1000 \
--save_steps 1000 \
--seed 42 \
--data_cache_dir ./data/cache/ \
--warmup_pct 0.1 \
--overwrite_output_dir \
--evaluate_during_training \
--save_mem \
# --fp16 \
# --fp16_opt_level O1

