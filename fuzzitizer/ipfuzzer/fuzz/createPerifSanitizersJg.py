import os, re, shutil, subprocess, sys
import gzip
from pathlib import Path
import numpy as np
import xml.etree.ElementTree as et

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _directory in (
    _REPO_ROOT, _REPO_ROOT / "fuzz", _REPO_ROOT / "utils",
    _REPO_ROOT / "benchmarks"):
  if str(_directory) not in sys.path:
    sys.path.insert(0, str(_directory))

import config
from configManager import getCONFIG
import FSMSanitizer, ZEROSanitizer
import config_sanitizers as SANS
import fuzz_utils as TU


def qualifiedSignal(tbModName, signal):
  signal = signal.strip('{}')
  if signal.startswith(f"{tbModName}."):
    return signal
  return f"{tbModName}.{signal}"


def qualifyJasperResetExpression(tbModName, expression):
  signalPattern = re.compile(
      r"(?<![A-Za-z0-9_$'.])"
      r"([A-Za-z_][A-Za-z0-9_$]*(?:\[[^\]]+\])?"
      r"(?:\.[A-Za-z_][A-Za-z0-9_$]*(?:\[[^\]]+\])?)*)")

  def qualify(match):
    signal = match.group(1)
    if signal.startswith(f"{tbModName}."):
      return signal
    return f"{tbModName}.{signal}"

  return signalPattern.sub(qualify, expression)


def parseRegisterResetMetadata(lines, tbModName):
  resets = {}
  register = None
  expression = None
  for line in lines:
    line = line.strip()
    if line.startswith('IPFUZZ_REG_RESET_BEGIN:'):
      register = line.partition(':')[2].strip()
      expression = None
    elif register is not None and line.startswith('IPFUZZ_REG_RESET_EXPR:'):
      expression = line.partition(':')[2].strip()
    elif register is not None and line.startswith('IPFUZZ_REG_RESET_END:'):
      endRegister = line.partition(':')[2].strip()
      if endRegister == register and expression:
        resets[qualifiedSignal(tbModName, register)] = (
            qualifyJasperResetExpression(tbModName, expression))
      register = None
      expression = None
  return resets


def parseOneTimeMetadata(lines, tbModName, topOutputs, outputInterfaces,
                         tbClkSignal):
  records = []
  record = None
  topOutputs = set(topOutputs)
  interfaces = {}
  for interface in outputInterfaces:
    match = re.fullmatch(r'([^\[.]+)\[(\d+):(\d+)\]', interface['port'])
    assert match, f"one-time output port requires an explicit range: {interface['port']}"
    highBit, lowBit = int(match.group(2)), int(match.group(3))
    assert highBit >= lowBit, f"invalid one-time output range: {interface['port']}"
    interfaces[match.group(1)] = {
        'port': interface['port'],
        'data': qualifiedSignal(tbModName, interface['port']),
        'data_width': highBit - lowBit + 1,
        'clock': qualifiedSignal(tbModName, tbClkSignal),
        'valid': interface['valid'],
    }

  for line in lines:
    line = line.strip()
    if line.startswith('IPFUZZ_TARGET_BEGIN: '):
      record = {
          'tarSig': qualifiedSignal(tbModName, line.split(': ', 1)[1]),
          'width': None,
          'fanin': [],
          'fanout': [],
      }
    elif record is not None and line.startswith('IPFUZZ_TARGET_WIDTH: '):
      record['width'] = int(line.split(': ', 1)[1])
    elif record is not None and line.startswith('IPFUZZ_FANIN: '):
      match = re.match(r'IPFUZZ_FANIN: (.+) \| width=(\d+) \| clock=(.+)', line)
      if match:
        record['fanin'].append({
            'signal': qualifiedSignal(tbModName, match.group(1)),
            'width': int(match.group(2)),
            'clock': qualifiedSignal(tbModName, match.group(3)),
        })
    elif record is not None and line.startswith('IPFUZZ_FANOUT: '):
      match = re.match(r'IPFUZZ_FANOUT: (.+) \| width=(\d+)', line)
      if match:
        signal = match.group(1).strip('{}')
        port_match = re.match(r'([^\[.]+)', signal)
        if port_match:
          record['fanout'].append({
              'signal': signal,
              'port': port_match.group(1),
              'width': int(match.group(2)),
          })
    elif record is not None and line.startswith('IPFUZZ_TARGET_END: '):
      selected = []
      selected_ports = set()
      for fanout in record.pop('fanout'):
        port = fanout['port']
        if fanout['width'] <= 1 or port not in topOutputs or port not in interfaces:
          continue
        if port not in selected_ports:
          selected.append(interfaces[port])
          selected_ports.add(port)
      record['interfaces'] = selected
      records.append(record)
      record = None

  return records


def runJasperGold(simDir, jgTclFile, jgLogFile, debug=False):
  simDir = os.fspath(simDir)
  jgTclFile = os.fspath(jgTclFile)
  jgLogFile = os.fspath(jgLogFile)

  shutil.rmtree(os.path.join(simDir, 'jgproject'), ignore_errors=True)
  if os.path.isdir(jgLogFile) and not os.path.islink(jgLogFile):
    shutil.rmtree(jgLogFile)
  else:
    try:
      os.remove(jgLogFile)
    except FileNotFoundError:
      pass

  command = ['jg', '-no_gui', '-command', f'include {{{jgTclFile}}}; exit']
  if debug:
    completed = subprocess.run(command, cwd=simDir, stdout=subprocess.PIPE, text=True)
    output = completed.stdout or ''
    print(output, end='')
    with open(jgLogFile, 'w') as fp:
      fp.write(output)
  else:
    with open(jgLogFile, 'w') as fp:
      completed = subprocess.run(command, cwd=simDir, stdout=fp)

  return completed.returncode


class Design():
  def __init__(self, coreName):
    self.coreName = coreName 
    self.modList = []
    self.pkgList = []
    self.fileList = []
    self.modTb = None
    self.modBind = None
    self.insts = {}
    self.regList = {}
    self.numSanitizers = 0


  def parseVerilogDesignFile(self, verilogDesignFile, tbModName, bindModName, debug=False):
    """
    - this func gets the list of all modules, their ids, and corresponding instances
    - modules of package and other types are ignored
    <srcdef id="-12"  name="_vcs_msglog"  type="package"  chksum="3262157070"  >
      <srclocmult file_id="136"  start="17"  end="61"  />
      <srcinst id="-12"  name="_vcs_msglog"  pid="-1"  >
        <srcloc file_id="136"  lines="17"  />
      </srcinst>
    </srcdef>
    """
    verilogDesignData = gzip.open(verilogDesignFile, 'rb')
    tree = et.parse(verilogDesignData)
    root = tree.getroot()

    modElements = root.findall("srcdef")


    for child in modElements: 
      if child.attrib["type"] == "package": 
        package = Module(child.attrib["name"], child.attrib["type"], child.attrib["id"])
        package.modFileId = child.find('srclocmult').attrib["file_id"]
        self.pkgList.append(package)
      elif child.attrib["type"] == "module": 
        module = Module(child.attrib["name"], child.attrib["type"], child.attrib["id"])
        module.modFileId = child.find('srclocmult').attrib["file_id"]
        modInstElements = child.findall("srcinst")
        module.insts = {e.attrib["id"]: {"name": e.attrib["name"], "pid": e.attrib["pid"], "mid": child.attrib["id"]\
                                       , "path": None, "params": {}}\
                            for e in modInstElements}

        if module.modName == tbModName:
          self.modTb = module
        elif module.modName == bindModName:
          self.modBind = module
        else: 
          self.modList.append(module)
      else: 
        assert False, f"unknown file type found {child.attrib['type']}, {verilogDesignFile}"


  def parseVerilogSourceInfoFile(self, verilogSourceInfoFile, debug=False):
    """
    - links each module's id with their file paths
    <fileinfo name="/path/to/source_file.sv" id="5" />
    """

    verilogSourceInfoData = open(verilogSourceInfoFile, 'r')
    tree = et.parse(verilogSourceInfoData)
    root = tree.getroot()


    fileElements = root.findall("fileinfo")
    for fe in fileElements: 
      self.fileList.append([fe.attrib["id"], fe.attrib["name"]])



    for mod in self.modList + self.pkgList: 

      for fe in fileElements: 
        if fe.attrib["id"] == mod.modFileId: 
          mod.modFile = fe.attrib["name"]
          break


      assert mod.modFile != "", f"couldnt find the file path for {mod.modName} module"


  def createAbsoluteInstancePaths(self, debug=False):

    assert len(list(self.modTb.insts.keys())) == 1, f"number of instances of tb is not 1, {list(self.modTb.keys())}"
    for instId, instData in self.modTb.insts.items():
      self.insts[instId] = instData
      assert self.modTb.modName == instData["name"]\
                , f"tb module name and instance name are different, {self.modTb.modName},{instData['name']}"
    for mod in self.modList + [self.modBind]:
      for instId, instData in mod.insts.items(): 
        self.insts[instId] = instData

    instIds = [list(self.modTb.insts.keys())[0]]


    while instIds != []: 
      nextInstIds = []


      for instId in instIds: 
        instData = self.insts[instId]


        if instData["pid"] == "-1":


          instData["path"] = instData["name"]
        else: 
          instPid = instData['pid']
          assert "path" in self.insts[instPid], f"instance {instId}, {instData}'s parent doesnt have absolute path, {self.insts[instPid]}"
          instData["path"] = f"{self.insts[instPid]['path']}.{instData['name']}"


        for sinstId, sinstData in self.insts.items():
          if sinstData['pid'] == instId: nextInstIds.append(sinstId)
      instIds = nextInstIds


      for mod in self.modList: 
        for instId, instData in mod.insts.items(): 
          instData['path'] = self.insts[instId]['path']


  def parseVerilogInstanceParametersFile(self, verilogInstanceParametersFile):
    """
    - get the parameters, their values, and assign them to respective instances
    - line format: opn_dma_tb.perif_u.u_dma.CTRL_ABORT^A8  
    - parameter name can be a.b.c.d.e, but only a.b.c is instance path and d.e
      is the parameter. this happens if a for block is named d and has 
      parameter e declared inside it
    - beaware of cases like this: case1:
      - param is opn_aes2_tb.perif_u.aes2_interface.aes2_gcm_top.GFM_MULT
      - but there can be inst: opn_aes2_tb.perif_u.aes2_interface.aes2_gcm_top.GFM
      - so, param can go to GFM inst instead of aes2_gcm_top
    """

    if not os.path.isfile(verilogInstanceParametersFile): 
      return
    rePattern = f'^(.*)\\x01([0-9,a-f]+)\\n$'
    with open(verilogInstanceParametersFile, 'r') as fp: lines = fp.readlines()
    for line in lines:

      lineData = re.search(rePattern, line)
      paramFullName = lineData.group(1)
      paramValue = int(lineData.group(2), 16)


      instIdParam = None
      instName = ""
      for instId, instData in self.insts.items():
        if instData['path']+"." in paramFullName:
          if instName in instData['path']:
            instName = instData['path']
            instIdParam = instId
      assert instIdParam, f"no instances matching parameter value, {paramFullName}"

      paramName = paramFullName[len(instName)+1:]
      self.insts[instIdParam]['params'][paramName] = paramValue


    for mod in self.modList: 
      for instId, instData in mod.insts.items(): 
        instData['params'] = self.insts[instId]['params']

  def extractDesignWithJg(self, simDir, jgTclFile, jgLogFile, tbModName\
                        , topModName, topInstName, perifInputs, oneTimeRegs\
                        , oneTimeOutputInterfaces, tbClkSignal, debug=False): 

    projectRoot = os.environ['IPFUZZ_ROOT']
    socName = self.coreName.split('_', 1)[0]
    allowedRoots = [os.path.join(projectRoot, 'benchmarks', socName)\
                  , os.path.join(projectRoot, 'benchmarks', self.coreName)]
    flist = [i for i in self.fileList if TU.isProjectSource(i[1], simDir, allowedRoots)]
    perifFileListSortedIndices = np.argsort([int(id) for id,f in flist])
    perifFileListSorted = [flist[i][1] for i in perifFileListSortedIndices]
    perifFileString = '\\\n '.join(perifFileListSorted)


    perifDirList = [os.path.dirname(i) for i in perifFileListSorted]
    perifDirSet = set([i for i in perifDirList if i != ""])

    sd = min(perifDirSet, key=len)
    subDir = next((sd[:i] for i in range(len(sd)) if not all(s[i] == sd[i] for s in perifDirSet)), "")



    perifDirList = []
    for d in perifDirSet:
      perifDirList += [os.path.sep.join(d.split(os.path.sep)[:i]) for i in range(1, len(d.split(os.path.sep)) + 1)]
    perifDirSet = set([d for d in perifDirList if subDir in d])
    perifDirString = '+incdir+'+'\\\n +incdir+'.join(perifDirSet)

    oneTimeRegsList = "{" + ' '.join(oneTimeRegs) + "}"
    

    with open(jgTclFile, 'w') as fp: 
      fp.write(f"analyze -sv {perifDirString}\\\n {perifFileString}")

      fp.write(f"\nset_capture_elaborated_design on")
      fp.write(f"\nelaborate -top {tbModName}")
      fp.write(f"\nsave -elaborated_design jg_save_ela -force")
      fp.write(f"\nset inputs [get_design_info -module  {topModName} -list input]\n")
      fp.write(f"\nset outputs [get_design_info -module {topModName} -list output]\n")
      fp.write(f"\nset regs [get_design_info -list flop]\n")


      fp.write(f"""
        set regWidths {{}}
        set regClocks {{}}  
        foreach reg $regs {{
          lappend regWidths [get_signal_info -width $reg]
          set clkData [get_flop_info $reg -clock]
          set clkData [lindex $clkData 0]
          lappend regClocks [lindex $clkData 1]
          set rstData [lindex [get_flop_info -reset_pin -show_expr -silent $reg] 0]
          set rstExpr [lindex $rstData 1]
          set rstType [lindex $rstData 2]
          if {{$rstType eq "none"}} {{
            set rstExpr ""
          }}
          puts "IPFUZZ_REG_RESET_BEGIN: $reg"
          puts "IPFUZZ_REG_RESET_EXPR: $rstExpr"
          puts "IPFUZZ_REG_RESET_END: $reg"
         }}
        puts "REGS: $regs"
        puts "REGWIDTHS: $regWidths"
        puts "CLOCKNAMES: $regClocks"

        set ipWidths {{}}
        set opWidths {{}}
        foreach reg $inputs {{
          lappend ipWidths [get_signal_info -width {topInstName}.$reg]
         }}
        puts "INPUTS: $inputs"
        puts "IPWIDTHS: $ipWidths"
        foreach reg $outputs {{
          lappend opWidths [get_signal_info -width {topInstName}.$reg]
         }}
        puts "OUTPUTS: $outputs"
        puts "OPWIDTHS: $opWidths"
        get_design_info
        """)

      if len(oneTimeRegs) > 0: 
        fp.write(f"""
          set REGS [get_design_info -list register -silent]
          set TARGET_SIGNALS {oneTimeRegsList}
          foreach TARGET_SIGNAL $TARGET_SIGNALS {{
              set TARGET_SIGNAL_SIZE [get_signal_info -width $TARGET_SIGNAL]
              set FANINS [get_fanin -transitive $TARGET_SIGNAL -filter_out boundary -filter_out control -silent]
              set REG_FANIN [get_signal_list $REGS -intersection $FANINS]
              set FANOUTS [get_fanout -transitive $TARGET_SIGNAL -filter_out non_boundary -silent]
              puts "IPFUZZ_TARGET_BEGIN: $TARGET_SIGNAL"
              puts "IPFUZZ_TARGET_WIDTH: $TARGET_SIGNAL_SIZE"
              foreach FI $REG_FANIN {{
                  set FI_WIDTH [get_signal_info -width $FI]
                  set FI_CLOCK_DATA [lindex [get_flop_info $FI -clock] 0]
                  set FI_CLOCK [lindex $FI_CLOCK_DATA 1]
                  puts "IPFUZZ_FANIN: $FI | width=$FI_WIDTH | clock=$FI_CLOCK"
              }}
              foreach FO $FANOUTS {{
                  puts "IPFUZZ_FANOUT: $FO | width=[get_signal_info -width $FO]"
              }}
              puts "IPFUZZ_TARGET_END: $TARGET_SIGNAL"
          }}
          get_design_info
          """)
  

    runJasperGold(simDir, jgTclFile, jgLogFile, debug)



    keys = ['REGS', 'REGWIDTHS', 'CLOCKNAMES', 'INPUTS', 'OUTPUTS'\
                , 'IPWIDTHS', 'OPWIDTHS']
    jgData = {k:[] for k in keys}
    with open(jgLogFile, 'r') as fp: lines = fp.readlines()
    for line in lines: 
      for key in keys:
        if re.search(f"^{key}:", line): 
          lineData = re.search(f"^{key}: (.*)", line)
          jgData[key] = lineData.group(1).split()



    for key in ['REGS', 'CLOCKNAMES']:
      for i, reg in enumerate(jgData[key]): 
        if reg == []: continue
        if re.search("^{{.*}}", reg): jgData[key][i] = reg[2:-2]
        elif re.search("^{.*}", reg): jgData[key][i] = reg[1:-1]
      jgData[key] = [f"{tbModName}.{i}" for i in jgData[key]]
    

    self.regList = {}
    registerResets = parseRegisterResetMetadata(lines, tbModName)
    for reg, width, clk in zip(jgData['REGS'], jgData['REGWIDTHS'], jgData['CLOCKNAMES']): 
      self.regList[reg] = [width, clk, registerResets.get(reg)]

    self.oneTimeRegs = parseOneTimeMetadata(
        lines, tbModName, jgData['OUTPUTS'], oneTimeOutputInterfaces,
        tbClkSignal)


    confIpsSet = set( [pi['name'] for pi in perifInputs if pi['type'] in ['gen', 'fixed', 'clk', 'rst']] )
    confOpsSet = set( [pi['name'] for pi in perifInputs if pi['type'] == 'out'] )
    jgIpsSet = set( jgData['INPUTS'] )
    jgOpsSet = set( jgData['OUTPUTS'] )
    assert confIpsSet == jgIpsSet, f"inputs not matching, \n{confIpsSet}, \n\n{jgIpsSet}\n\n{confIpsSet-jgIpsSet}\n\n{jgIpsSet-confIpsSet}"
    assert confOpsSet == jgOpsSet, f"outputs not matching, \n{confOpsSet}, \n\n{jgOpsSet}\n\n{confOpsSet-jgOpsSet}\n\n{jgOpsSet-confOpsSet}"
    for pi in perifInputs:
      if not pi['type'] in ['gen', 'fixed', 'clk', 'rst', 'out']: continue
      if  pi['type'] in ['gen', 'fixed', 'clk', 'rst']:
        jgNbits = jgData['IPWIDTHS'][jgData['INPUTS'].index(pi['name'])]
      if  pi['type'] in ['out']:
        jgNbits = jgData['OPWIDTHS'][jgData['OUTPUTS'].index(pi['name'])]
      assert int(pi['nbits']) == int(jgNbits), f"bitwidth not matching for {pi}, {jgNbits}"


"""
- this class stores all info about each module
"""
class Module(object): 
  def __init__(self, modName, modType, modId):
    self.modName = modName
    self.modType = modType
    self.modId = modId
    self.modFileId = ""
    self.modFile = ""
    self.insts = {}
    self.ast = None
    self.directives = None
    self.seqAlwaysNodes = []
    self.modSignalsToRst = []
    self.rstMetaData = {}
    self.rstInstMetaData = {}
    self.rstSanitizers = []
    self.fsmParameterized = None
    self.fsmFsmNodes = {}
    self.fsmList = []
    self.fsmMetaData = {}
    self.fsmInstMetaData = {}
    self.fsmSanitizers = []

  def basicPrint(self): 
    print(self.modName, self.modType, self.insts)
    print(self.modFile)


def createSanitizersFile(sanitizersFile, bindModName, tbModName, bindInstName\
                       , tbRstSignal, tbClkSignal, sanitizerLines=[], numSanitizers=0, debug=False):


  if numSanitizers == 0: 
    sanitizerLines.append(f"// Dummy sanitizer to ensure cov file is generated")
    sanitizerLines.append(f"\nproperty p_dummy;")
    sanitizerLines.append(f"\n@(posedge {tbModName}.{tbClkSignal}) 1;\nendproperty;")
    sanitizerLines.append(f"\na_dummy: assert property(p_dummy);")


  preLines = [f"module {bindModName}\n"]
  preLines.append(f"  ({tbRstSignal});\n")
  preLines.append(f"  input {tbRstSignal};\n")
  preLines.append(f"\n// sanitizers here\n")


  postLines = [f"endmodule\n\n\n"]
  postLines.append(f"bind {tbModName}\n")
  postLines.append(f" {bindModName}\n")
  postLines.append(f" {bindInstName}\n")
  postLines.append(f"  (.{tbRstSignal} ({tbRstSignal}));\n")


  with open(sanitizersFile, 'w') as fp: 
    for line in preLines + sanitizerLines + postLines: fp.write(line)


def rebaseSanitizerLinesForSoc(sanitizerLines, tbModName, basePathMacro,
                               topInstanceName='perif_u', signalReplacements=None):
  rebasedLines = list(sanitizerLines)
  for source, target in sorted(
      (signalReplacements or {}).items(), key=lambda item: len(item[0]), reverse=True):
    signal = re.compile(
        rf'(?<![A-Za-z0-9_$\.]){re.escape(source)}(?![A-Za-z0-9_$])')
    rebasedLines = [signal.sub(target, line) for line in rebasedLines]

  topHierarchy = re.compile(
      rf'(?<![A-Za-z0-9_$\.]){re.escape(tbModName)}\.'
      rf'{re.escape(topInstanceName)}(?=\.|\b)')
  hierarchy = re.compile(rf'(?<![A-Za-z0-9_$\.]){re.escape(tbModName)}\.')
  rebasedLines = [
      hierarchy.sub(f'{basePathMacro}.', topHierarchy.sub(basePathMacro, line))
      for line in rebasedLines
  ]
  remaining = re.compile(rf'(?<![A-Za-z0-9_$]){re.escape(tbModName)}\.')
  if any(remaining.search(line) for line in rebasedLines):
    raise ValueError(f"standalone testbench hierarchy remains for {tbModName}")
  return rebasedLines


def createSocSanitizersFile(sanitizersFile, bindModName, tbModName,
                            socBindModName, bindInstName, tbRstSignal,
                            tbClkSignal, basePath, sanitizerLines=None,
                            numSanitizers=0, debug=False,
                            signalReplacements=None,
                            bindSignalReplacements=None):
  sanitizerLines = list(sanitizerLines or [])
  if numSanitizers == 0:
    sanitizerLines += [
        "// Dummy sanitizer to ensure cov file is generated",
        "\nproperty p_dummy;",
        f"\n@(posedge {tbModName}.{tbClkSignal}) 1;\nendproperty;",
        "\na_dummy: assert property(p_dummy);",
    ]
  sanitizerLines = rebaseSanitizerLinesForSoc(
      sanitizerLines, tbModName, '`BASE_PATH',
      signalReplacements=signalReplacements)

  lines = [f"`define BASE_PATH {basePath}\n", f"module {bindModName}\n"]
  lines += [f"  ({tbRstSignal});\n", f"  input {tbRstSignal};\n"]
  lines += ["\n// sanitizers here\n"]
  lines += sanitizerLines
  bindRstSignal = (bindSignalReplacements or {}).get(
      tbRstSignal, tbRstSignal)
  lines += ["endmodule\n\n\n", f"bind {socBindModName}\n",
            f" {bindModName}\n", f" {bindInstName}\n",
            f"  (.{tbRstSignal} ({bindRstSignal}));\n",
            "`undef BASE_PATH\n"]

  os.makedirs(os.path.dirname(os.fspath(sanitizersFile)), exist_ok=True)
  with open(sanitizersFile, 'w') as fp:
    fp.writelines(lines)


def createConfiguredSanitizerFiles(CONFIG, sanitizerLines=None, numSanitizers=0):
  sanitizerLines = list(sanitizerLines or [])
  createSanitizersFile(
      CONFIG.CORE.pt['sanitizers_sva_file_path'], CONFIG.CORE.bind_module,
      CONFIG.CORE.tb_module, CONFIG.CORE.bind_instance_name,
      CONFIG.CORE.tb_rst_signal, CONFIG.CORE.tb_clk_signal,
      list(sanitizerLines), numSanitizers)

  socFile = CONFIG.CORE.pt.get('soc_sanitizers_sva_file_path')
  if socFile:
    bindModule = CONFIG.CORE.bind_module
    bindModuleBase = bindModule[:-len('_v_dut')] if bindModule.endswith('_v_dut') else bindModule
    socBindInstName = f"i_{bindModuleBase}_bind_dut"
    createSocSanitizersFile(
        socFile, CONFIG.CORE.bind_module, CONFIG.CORE.tb_module,
        CONFIG.CORE.soc_sanitizer_bind_module,
        socBindInstName,
        CONFIG.CORE.tb_rst_signal, CONFIG.CORE.tb_clk_signal,
        CONFIG.CORE.soc_sanitizer_base_path, sanitizerLines, numSanitizers,
        signalReplacements=getattr(
            CONFIG.CORE, 'soc_sanitizer_signal_map', {}),
        bindSignalReplacements=getattr(
            CONFIG.CORE, 'soc_sanitizer_bind_signal_map', {}))



def createRstSanitizers(design, rstSanitizerTemplates, rstMetaUserData, debug=False):




  design.rstMetaData = {key: [] for key in rstSanitizerTemplates.keys()}
  sanitizerLines = []


  masterRstSignal = rstMetaUserData['InRstDom'][0]["masterRstSignal"]
  rstSanitizerType = 'InRstDom'
  for reg, regData in design.regList.items(): 
    sanitizerId = f"{rstSanitizerType}_{design.numSanitizers:04d}"
    design.rstMetaData[rstSanitizerType].append({'clk': regData[1]
                                             , 'rstType': f""\
                                             , 'rst': masterRstSignal\
                                             , 'sig': reg\
                                             , 'stype': rstSanitizerType
                                             , 'id': sanitizerId
                                              })
    design.numSanitizers+=1
      


  sanitizerLines = []
  for rstSanitizerType, templateValuesList in design.rstMetaData.items():
    for templateValues in templateValuesList: 
      sanitizerLines.append(rstSanitizerTemplates[rstSanitizerType].substitute(**templateValues))

  return sanitizerLines


def main(empty_only=False):


  CONFIG = getCONFIG(config, configType='file')


  verilogDesignFile = CONFIG.CORE.pt['verilog_design_file_path'].substitute(tno=0)
  verilogSourceInfoFile = CONFIG.CORE.pt['verilog_source_info_file_path'].substitute(tno=0)
  fsmVerilogShapeXMLFile = CONFIG.CORE.pt['fsm_verilog_shape_file_path'].substitute(tno=0)
  verilogInstanceParametersFile = CONFIG.CORE.pt['verilog_instance_parameters_file_path'].substitute(tno=0)


  clkSubstrings = CONFIG.CORE.clk_substrings
  rstSubStrings = CONFIG.CORE.rst_substrings
  rstMetaUserData = {}

  masterRstSignal = f"!{CONFIG.CORE.tb_module}.{CONFIG.CORE.tb_rst_signal}"
  rstMetaUserData['InRstDom'] = [{"masterRstSignal": masterRstSignal}]
  masterClkSignal = f"{CONFIG.CORE.tb_module}.{CONFIG.CORE.tb_clk_signal}"
  debugEnSig = CONFIG.CORE.debug_enable_signal
  oneTimeRegs = CONFIG.CORE.one_time_regs
  oneTimeOutputInterfaces = CONFIG.CORE.one_time_output_interfaces


  rstSanitizerTemplates = SANS.rstSanitizerTemplates
  fsmSanitizerTemplates = SANS.fsmSanitizerTemplates
  zeroSanitizerTemplates = SANS.zeroSanitizerTemplates




  createConfiguredSanitizerFiles(CONFIG)
  if empty_only:
    return 



  design = Design(CONFIG.core_name)

  design.parseVerilogDesignFile(verilogDesignFile, CONFIG.CORE.tb_module, CONFIG.CORE.bind_module)

  design.parseVerilogSourceInfoFile(verilogSourceInfoFile)

  design.createAbsoluteInstancePaths()

  design.parseVerilogInstanceParametersFile(verilogInstanceParametersFile)

  design.extractDesignWithJg(CONFIG.CORE.pt['perif_sim_dir']\
                            , CONFIG.CORE.pt['perif_jg_tcl_file']\
                            , CONFIG.CORE.pt['perif_jg_tcl_log_file']\
                            , CONFIG.CORE.tb_module, CONFIG.CORE.top_module\
                            , CONFIG.CORE.top_instance_name, CONFIG.CORE.input_format_info\
                            , CONFIG.CORE.one_time_regs, oneTimeOutputInterfaces\
                            , CONFIG.CORE.tb_clk_signal, False)


  sanitizerLines = []
  sanitizerLines += createRstSanitizers(design\
                      , rstSanitizerTemplates, rstMetaUserData, False)
  
  numRstSanitizers = design.numSanitizers
  print(f"{CONFIG.core_name}: RstSanitizers: ", numRstSanitizers)

  sanitizerLines += FSMSanitizer.createFSMSanitizers(design\
                      , fsmVerilogShapeXMLFile, fsmSanitizerTemplates\
                      , rstSubStrings, clkSubstrings, masterRstSignal, masterClkSignal\
                      , 'jg', CONFIG.CORE.fsm_init_value_info[CONFIG.core_name]\
                      , CONFIG.CORE.ignore_fsms[CONFIG.core_name], False)
  numFsmSanitizers = design.numSanitizers - numRstSanitizers
  print(f"{CONFIG.core_name}: FsmSanitizers: ", numFsmSanitizers)


  numSanitizersPast = design.numSanitizers
  sanitizerLines += ZEROSanitizer.createZEROSanitizers(design\
                      , zeroSanitizerTemplates, debugEnSig\
                      , 'jg', True)
  numZeroSanitizers = design.numSanitizers - numSanitizersPast
  print(f"{CONFIG.core_name}: ZeroSanitizers: ", numZeroSanitizers)



  createConfiguredSanitizerFiles(CONFIG, sanitizerLines, design.numSanitizers)

if __name__ == '__main__':
  main()
