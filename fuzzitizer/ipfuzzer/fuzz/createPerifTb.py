import os, re, sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _directory in (
    _REPO_ROOT, _REPO_ROOT / "fuzz", _REPO_ROOT / "utils",
    _REPO_ROOT / "benchmarks"):
  if str(_directory) not in sys.path:
    sys.path.insert(0, str(_directory))

import config
from configManager import getCONFIG


def createTbFile(tbFile, coreName, tb1File, tb2File, tb3File\
               , perifParams, perifInputs, coreTopModName\
               , tbClkSignal, tbRstSignal\
               , tbModName, topInstName, clock_period, max_sim_cycles):


  lines = [f"module {tbModName} #(\n"]
  lines.append(f"      parameter int unsigned MAX_CYCLES = {max_sim_cycles}\n")
  lines.append(f"    , parameter WAVE_ENABLE = 0\n")
  lines.append(f"    , parameter CLOCK_PERIOD = {clock_period}\n")
  lines.append(f"  ) ();\n")
  lines.append(f"\n")


  for perifParam in perifParams:
    lines.append(f"  localparam {perifParam['type']} {perifParam['name']} = {perifParam['value']};\n")
  lines.append("\n")


  lines.append(f"  // variables\n")
  lines.append(f"  logic {tbClkSignal}, {tbRstSignal};\n")
  for pi in perifInputs:
    if pi['type'] in ['gen', 'out']:
      lines.append(f"  logic [{pi['nbits']-1}:0] {pi['name']};\n")
  lines.append("\n\n")


  with open(tb1File, 'r') as fp: lines1 = fp.readlines()
  lines += lines1


  perifGenInputs = [pi for pi in perifInputs if pi['type'] in ['gen']]

  for pi in perifGenInputs:
    lines.append(f"    {pi['name']} = {{{pi['nbits']}{{1'b0}}}};\n")
  lines.append("\n")


  with open(tb2File, 'r') as fp: lines2 = fp.readlines()
  lines += lines2


  perifGenInputNames = [pi['name'] for pi in perifGenInputs]
  lines.append(f'      $fscanf(fp, "' + '%h,'*(len(perifGenInputNames)-1) + '%h", ')
  lines.append(", ".join(perifGenInputNames) + ');\n')
  lines.append(f'      $display("time=%8d, Read ' + "=%h, ".join(perifGenInputNames))
  lines.append('=%h", $time, ' + ", ".join(perifGenInputNames) + ');\n')


  with open(tb3File, 'r') as fp: lines3 = fp.readlines()
  lines += lines3


  noInputSignals = 0
  lines.append(f'  {coreTopModName} #(\n    '    )
  paramDecls = [f".{p['name']}({p['name']})" for p in perifParams]
  lines.append(',\n    '.join(paramDecls))
  lines.append('\n')
  lines.append(f'  ) {topInstName} (\n')




  perifClkSignal = next((pi['name'] for pi in perifInputs if pi['type'] == 'clk'), None)
  assert perifClkSignal, f"couldnt find clock signal for {coreName}, {perifInputs}"
  

  perifRstInput = next((pi for pi in perifInputs if 'rst' == pi['type']), None)
  assert perifRstInput, f"couldnt find rst signal for {coreName}, {perifInputs}"
  perifRstSignal = perifRstInput['name'] 
  if perifRstInput['edge'] == 'posedge': perifRstSignal = f"~{perifRstSignal}"


  lines.append(f'      .{perifClkSignal} ({tbClkSignal})\n')
  lines.append(f'    , .{perifRstSignal} ({tbRstSignal})\n')
  noInputSignals += 2
  for pi in perifInputs:
    if not pi['type'] in ['clk', 'rst']:
      if pi['type'] in ['gen', 'out']:
        if 'varType' in pi.keys() and pi['type'] in ['gen']:
          piAssign = f"{pi['varType']}'({pi['name']})"
        else: 
          piAssign = pi['name'] 
      elif pi['type'] == 'fixed':
        piAssign = pi['value']
      else: 
        assert False, f"new type input signal found in {coreName}, {pi}, {perifInputs}"
      lines.append(f'    , .{pi["name"]} ( {piAssign} )\n')
      noInputSignals += pi['nbits']*(pi['type'] in  ['gen', 'fixed'])
  lines.append("  );\n\n")
  lines.append("endmodule\n")
  print(f"{coreName}: {noInputSignals}");


  with open(tbFile, 'w') as fp: 
    for line in lines: fp.write(line)


def main():


  CONFIG = getCONFIG(config, configType='file')


  createTbFile(CONFIG.CORE.pt["tb_file_path"], CONFIG.core_name\
                            , CONFIG.CORE.pt["tb_1_file_path"]\
                            , CONFIG.CORE.pt["tb_2_file_path"]\
                            , CONFIG.CORE.pt["tb_3_file_path"]\
                            , CONFIG.CORE.params_info, CONFIG.CORE.input_format_info\
                            , CONFIG.CORE.top_module\
                            , CONFIG.CORE.tb_clk_signal, CONFIG.CORE.tb_rst_signal\
                            , CONFIG.CORE.tb_module, CONFIG.CORE.top_instance_name\
                            , CONFIG.CORE.clock_period, CONFIG.CORE.max_sim_cycles)


if __name__ == '__main__':
  main()
