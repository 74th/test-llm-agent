## reasoning budget 設定なし

```
#!/bin/bash
set -xe
/opt/llama-b9616/llama-server \
  --host 0.0.0.0 --port 30323 \
  --parallel 1 \
  -c 65536 \
  -hf unsloth/gemma-4-26B-A4B-it-qat-GGUF:UD-Q4_K_XL \
  --spec-type draft-mtp --spec-draft-n-max 4 \
  -ngl 999 -fa on

```

- restored context checkpoint で 3119 となっているので、KVキャッシュは効いてそう。
- draft acceptance = 0.43722 ( 1156 accepted /  2644 generated)


```
691.29.134.241 I srv  get_availabl: prompt cache update took 648.06 ms
691.29.134.449 I slot launch_slot_: id  0 | task 41080 | processing task, is_child = 0
691.29.134.469 I slot update_slots: id  0 | task 41080 | Checking checkpoint with [1680, 3118] against 2260...
691.29.140.975 W slot update_slots: id  0 | task 41080 | restored context checkpoint (pos_min = 1680, pos_max = 3118, n_tokens = 3119, n_past = 3118, size = 200.012 MiB)
691.30.148.468 I slot create_check: id  0 | task 41080 | created context checkpoint 8 of 32 (pos_min = 2162, pos_max = 3697, n_tokens = 3698, size = 200.012 MiB)
691.30.541.694 I reasoning-budget: activated, budget=2147483647 tokens
691.32.666.227 I slot print_timing: id  0 | task 41080 | n_decoded =    102, tg =  46.69 t/s
691.35.719.156 I slot print_timing: id  0 | task 41080 | n_decoded =    240, tg =  45.82 t/s
691.38.739.826 I slot print_timing: id  0 | task 41080 | n_decoded =    376, tg =  45.53 t/s
691.41.795.406 I slot print_timing: id  0 | task 41080 | n_decoded =    516, tg =  45.61 t/s
691.44.834.292 I slot print_timing: id  0 | task 41080 | n_decoded =    654, tg =  45.57 t/s
691.47.875.044 I slot print_timing: id  0 | task 41080 | n_decoded =    793, tg =  45.59 t/s
691.50.920.354 I slot print_timing: id  0 | task 41080 | n_decoded =    920, tg =  45.01 t/s
691.53.922.300 I slot print_timing: id  0 | task 41080 | n_decoded =   1054, tg =  44.96 t/s
691.56.929.438 I slot print_timing: id  0 | task 41080 | n_decoded =   1208, tg =  45.68 t/s
691.59.967.198 I slot print_timing: id  0 | task 41080 | n_decoded =   1364, tg =  46.26 t/s
692.01.369.526 I reasoning-budget: deactivated (natural end)
692.03.006.887 I slot print_timing: id  0 | task 41080 | n_decoded =   1527, tg =  46.95 t/s
692.06.041.286 I slot print_timing: id  0 | task 41080 | n_decoded =   1680, tg =  47.24 t/s
692.08.138.255 I slot print_timing: id  0 | task 41080 | prompt eval time =    1347.31 ms /   740 tokens (    1.82 ms per token,   549.24 tokens per second)
692.08.138.258 I slot print_timing: id  0 | task 41080 |        eval time =   37656.44 ms /  1817 tokens (   20.72 ms per token,    48.25 tokens per second)
692.08.138.259 I slot print_timing: id  0 | task 41080 |       total time =   39003.76 ms /  2557 tokens
692.08.138.260 I slot print_timing: id  0 | task 41080 |    graphs reused =      40595
692.08.138.261 I slot print_timing: id  0 | task 41080 | draft acceptance = 0.43722 ( 1156 accepted /  2644 generated)
692.08.138.278 I statistics        draft-mtp: #calls(b,g,a) =  117  41235  41235, #gen drafts =  41235, #acc drafts = 30072, #gen tokens = 164863, #acc tokens = 82366, dur(b,g,a) = 0.196, 328342.573, 23.584 ms
692.08.138.648 I slot      release: id  0 | task 41080 | stop processing: n_tokens = 5675, truncated = 0
692.08.138.673 I srv  update_slots: all slots are idle
^C781.44.416.310 I srv    operator(): operator(): cleaning up before exit...
```

## reasoning budget = 1024

```
#!/bin/bash
set -xe
/opt/llama-b9616/llama-server \
  --host 0.0.0.0 --port 30323 \
  --parallel 1 \
  --reasoning-budget 1024 \
  -b 8192 \
  -ub 2048 \
  -c 65536 \
  -hf unsloth/gemma-4-26B-A4B-it-qat-GGUF:UD-Q4_K_XL \
  --spec-type draft-mtp --spec-draft-n-max 4 \
  -ngl 999 -fa on
```
