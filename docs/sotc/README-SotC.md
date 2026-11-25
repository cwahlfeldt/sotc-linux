# Shadow of the Colossus — PC (port nativo)

Port nativo do **Shadow of the Colossus** de PS4 (CUSA08809, versão EU 1.01, ou CUSA08034,
versão US 1.00) para **Linux**.
O código do jogo roda direto na CPU. Isto não é um emulador completo: há um carregador e as
funções de sistema de que o jogo precisa. A GPU usa o núcleo de vídeo Vulkan do fork
shadPS4 SotC. A base é o [bloodborne_pc](https://github.com/Supermedo/bloodborne_pc) (GPL-2.0).

Este repositório **não contém o jogo nem firmware da Sony**. Você precisa ter os seus.

## Requisitos

- Linux x86-64, processador com AVX, BMI1, LZCNT e MOVBE (Intel Haswell / AMD Zen ou mais novo)
  e GPU com driver Vulkan 1.3 (Mesa RADV ou ANV, ou o da NVIDIA).
- As ferramentas de compilação e as bibliotecas listadas no `README.md` (Arch / CachyOS: uma
  linha de `pacman`), e Python 3.
- O **seu dump** do jogo CUSA08809 ou CUSA08034 (pasta com `eboot.bin`, `sce_module`, `sce_sys`...).
- **Som:** desde a 0.75 o port tem um **mixer de som embutido**, e o jogo tem som sem nada do
  console. Opcional: `libSceNgs2.sprx` e `libSceUlt.sprx` do **seu próprio console**, decriptados
  (os mesmos da pasta `user/sys_modules` do shadPS4; num PS4 com GoldHEN ficam em
  `/system/common/lib/`, FTP na porta 2121). Com eles, o som é o do firmware:
  `SOTC_SYS_MODULES=/pasta/com/os/sprx` no `sotc.ini`.

## Como jogar

1. Deixe o dump ao lado desta pasta (`../CUSA08809` ou `../CUSA08034`) ou escreva
   `SOTC_GAME_DIR=/caminho/do/jogo` no `sotc.ini`. A atualização 1.01 (`CUSA08809-UPDATE`) e as
   DLCs (`CUSA08809-DLC`) são achadas ao lado do jogo.
2. Rode `bash run.sh`: ele compila o port (`out/bb-probe` e `out/gpu/libbbgpu.so`) e abre o jogo.
   `python3 sotc.py` abre sem compilar.

Na primeira vez a imagem do jogo é preparada, o que leva alguns segundos. Isso só se repete
quando o jogo ou os módulos mudam. Os saves e o cache de shaders ficam em `user/`, o registro da
sessão em `user/last_run.log`.

O que se muda no menu do jogo (F1) fica guardado em `user/settings.json` e vale na próxima
abertura, com os mesmos padrões das versões para Windows (filtro 16x, texturas altas, sem os
logos...). As opções também podem ser variáveis de ambiente ou linhas `NOME=valor` no `sotc.ini`,
que valem mais que o arquivo; a lista completa está no começo do `sotc.py`.

## Imagem e desempenho

No `sotc.ini` (ou no ambiente):

- **Saída** (`SOTC_OUTPUT_RES=2560x1440`, por exemplo): 720p, 1080p, 1440p ou 4K. O jogo
  renderiza em 1080p, como no PS4, e a imagem é ampliada para a saída com **FSR 1** + nitidez
  (RCAS) ou bilinear. A janela nunca passa de 90% da tela; a tela cheia usa o monitor inteiro.
- **60 FPS** (`SOTC_MODES=fps60` e `SOTC_FPS_CAP=off`; experimental): tira o limite de 30 FPS
  do jogo (patch GoldHEN de illusion), com vblank a 120 Hz.
- **Reutilização de binds** (ligada por padrão; `SOTC_FAST_BIND=0` desliga): pula
  a remontagem dos descritores quando o desenho seguinte usa o mesmo pipeline, recursos e
  uniforms. Medido no Santuário: ~25 → 30 FPS. Na 0.60.5 deixava pontos pretos em grade no chão de
  areia; com a correção o chão de areia do demo ficou limpo.
- **Texturas nítidas** (`af16` em `SOTC_MODES`, por exemplo `SOTC_MODES=fps60,af16`): filtro
  anisotrópico 16x, quase sem custo.
- **HDR** (`hdr` em `SOTC_MODES`): saída HDR10 com a renderização HDR do próprio jogo; o desktop
  precisa oferecer HDR. O branco fica em 200 nits (`SOTC_HDR_WHITE` muda). Funciona com FSR 1 e DLSS.
- **Modo PS4 Pro** (`SOTC_NEO=1`): o jogo se vê num PS4 Pro e oferece no próprio menu (Opções > Apresentação)
  o Modo Grafismo **Cinematográfico** (1440p, mais detalhe) ou **Desempenho**. É mais pesado:
  ~25 FPS no campo aberto.
- **Efeitos** (`fx_vignette=0`, `fx_fog=0`, `fx_ssao=0` no `sotc.ini`, ou no menu do jogo):
  vinheta, névoa atmosférica e oclusão ambiente (SSAO) podem ser desligados. O motion blur, o
  brilho e os filtros ficam no menu do próprio jogo.
- **Cvars do motor** (`SOTC_CVARS="NOME=valor NOME=valor"`): variáveis do motor Bluepoint, para
  quem quer experimentar.

Os modos de patch valem para a versão EU 1.01 e para a US 1.00 (o executável é o mesmo); em
outra versão eles não são aplicados. Cada versão tem os seus saves (`user/savedata/1/CUSA08809`
ou `CUSA08034`) e só usa DLCs da mesma região.

## Controles

**Mouse:** clique na janela do jogo para capturar o mouse, que passa a girar a câmera; Esc ou
trocar de janela solta o mouse. Botão esquerdo = R1 (agarrar), direito = □ (atacar),
meio = L1. Sensibilidade e inversão ficam no menu do jogo (F1). Para remapear os botões
do mouse, use `mouse.<entrada>=left,right,middle,x1,x2`.

**Remapear (`sotc.ini`):** uma linha por entrada, com várias opções separadas por vírgula (vazio =
sem tecla). `key.<entrada>=` troca as teclas (nomes do SDL, como `Q`, `Left Shift`, `Space`) e
`mouse.<entrada>=` os botões do mouse. Entradas: `cross circle square triangle l1 r1 l2 r2 l3 r3
options touchpad touchpad_right up down left right move_up move_down move_left move_right look_up
look_down look_left look_right`. Exemplos: atacar com o botão esquerdo e o raio da espada com o
direito: `mouse.square=left` e `mouse.l1=right` (e `mouse.r1=` para soltar o R1); L1/R1 em outras
teclas: `key.l1=Q` e `key.r1=E`.

Um controle (DualShock 4, DualSense, Xbox...) é usado automaticamente. Com vários conectados,
escolha um com `BB_GAMEPAD=` (o nome ou parte dele) no `sotc.ini`. O teclado funciona
junto com o controle:

| Teclado | PS4 |
|---|---|
| W A S D | analógico esquerdo |
| setas | analógico direito (câmera) |
| Espaço | ✕ |
| Shift esquerdo | ○ |
| E | □ |
| Q | △ |
| 1 / 3 | L1 / R1 |
| R / F | L2 / R2 |
| Z / C | L3 / R3 |
| Enter | Options |
| I J K L | direcional |
| Tab / Backspace | touchpad (esquerda / direita) |

O controle também pode ser remapeado no `sotc.ini`, por exemplo `pad.circle=b`.
As entradas são:

- botões: `cross circle square triangle l1 r1 l2 r2 l3 r3 options touchpad touchpad_right`;
- direcional: `up down left right`;
- no teclado, os analógicos: `move_up` `move_down` `move_left` `move_right` e
  `look_up` `look_down` `look_left` `look_right`.

## Estado

Funcionam: logos, abertura, menus com texto, carregar save, exploração a cavalo,
som (com os módulos do usuário).

Desempenho medido no Santuário da Adoração, jogando, modo 60 FPS, i5-13600KF + RX 6650 XT:
~72 FPS (`tools/sotc_bench_gameplay.py`). No modo normal o jogo roda travado em 30 FPS, como no PS4.

## Perguntas comuns

- **DirectX 11/12?** Não. O núcleo de vídeo (shadPS4) traduz a GPU do PS4 para Vulkan; os
  shaders do jogo viram SPIR-V. Toda placa de vídeo com DirectX 12 recente também tem Vulkan
  1.3: atualize o driver. Um modo DirectX exigiria reescrever o núcleo de vídeo inteiro.
- **Placas AMD e Intel?** As otimizações valem para qualquer placa, menos duas que só ligam
  sozinhas na NVIDIA (o envio periódico de trabalho à GPU e as leituras antecipadas). Para
  testá-las na AMD ou Intel: `SOTC_FLUSH_US=1000` e `SOTC_RB_AHEAD=1` no `sotc.ini`; se a tela
  ficar preta, tire as duas linhas.
- **Preciso de arquivos do console para ter som?** Não, desde a 0.75: o mixer embutido do port
  toca o som. `libSceNgs2.sprx` e `libSceUlt.sprx` (firmware da Sony, que não pode ser
  distribuído) continuam opcionais; com eles, o som é o do firmware.

## Créditos

- [bloodborne_pc](https://github.com/Supermedo/bloodborne_pc) (bbport, deadinside28 e forks): carregador
  e runtime nativo, base deste port.
- [shadPS4](https://github.com/shadps4-emu/shadPS4) e o fork shadPS4 SotC: núcleo de vídeo Vulkan.
- [Pink-shadPS4](https://github.com/luizgustavs/Pink-shadPS4) (luizgustavs): as cvars de culling, a proteção
  do heap do jogo contra leituras da GPU (`bpe_heap_guard`), o flush periódico, as leituras antecipadas,
  o marcador de espera e o gravador de comandos Vulkan em thread própria (`cp_record_thread`).

## Diagnóstico

Estas variáveis de ambiente ajudam a investigar problemas:

| Variável | Efeito |
|---|---|
| `SOTC_FPS=1` | taxa de quadros a cada 5 s |
| `BB_READBACKS=0/1/2` | leituras da GPU; o padrão 2 é o exigido pelo jogo |
| `SOTC_FAST_BIND=0` | desliga o reaproveitamento de binds de descritores entre desenhos iguais (padrão: ligado) |
| `SOTC_RECORD_THREAD=0` | grava os comandos Vulkan na própria thread de comandos (padrão: thread própria) |
| `SOTC_INDIRECT_DIRECT=0` | mantém indiretos os draws cujos argumentos estão na CPU |
| `SOTC_WAIT_MARKER=1/2` | esperas pela GPU consultam um marcador escrito por ela (experimental) |
| `SOTC_CMD_STATS=1/2` | draws e dispatches por quadro (2: shaders de compute mais usados) |
| `SOTC_AMD_WAVE32=1` | só AMD, para testar nas GCN (RX 470-590, Vega, integradas): os shaders são convertidos para 32 lanes, como faz a camada SotC-AMD-Fix (personagens piscando em branco). O cache de shaders é refeito; o log mostra `GPU: AMD wave32 on`. De Lucas-blip-png |
| `SOTC_SLOW_BUILD_MS=500` | o log mostra `SOTC SLOW BUILD` para cada pipeline construído em segundo plano (ou esperado pela gravação de comandos) que levou esse tempo ou mais; `SOTC SYNC PIPELINE` mostra os construídos na thread de comandos acima de 30 ms (`SOTC_SYNC_PIPELINE_MS`). Para as travadas longas nas placas Intel Arc |
| `SOTC_HDR_WHITE=nits` | com HDR: o branco do jogo em nits (padrão 200; a saída do próprio jogo tem ~100) |
| `SOTC_EVICT_ASYNC=0` | a devolução de memória fria das arenas espera a GPU no processador de comandos, como antes (~44 ms por vez) |
| `SOTC_UI_HIRES=0` | com DLSS, a interface (textos, logos, HUD) volta a ser desenhada na resolução de renderização e ampliada, em vez de na resolução de saída |
| `SOTC_WINDOW_BEHIND=1` | automated tests: the window opens without asking for the focus (on Linux the compositor decides; COSMIC focuses it anyway) |
| `SOTC_PCORES=0` | Linux, processadores Intel com núcleos P e E (12ª geração em diante): as threads da GPU (processador de comandos, desenho e gravação) voltam a rodar em qualquer núcleo (padrão: só nos núcleos P, onde rendem mais) |
| `SOTC_PROFILE=nome` | amostra a thread com esse nome a cada ~1 ms, de `SOTC_PROFILE_DELAY` s (padrão 20) por `SOTC_PROFILE_SECONDS` s (padrão 15), e lista onde ela gasta tempo. No Linux o nome são os 15 primeiros caracteres (`shadPS4:GpuComm`, `shadPS4:GpuDraw`, `shadPS4:GpuReco`); `SOTC_PROFILE_OUT=arquivo` grava as amostras para `tools/profile_functions.py arquivo out/gpu/libbbgpu.so`; `SOTC_THREAD_TIMES=1` mostra o tempo de CPU de cada thread na mesma janela |
