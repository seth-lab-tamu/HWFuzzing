
import re


def debugSignalOwner(debugEnSig):
  signals = re.findall(
      r'(?<![:\w])(?:[A-Za-z_]\w*\.)+[A-Za-z_]\w*(?:\[[^\]]+\])?',
      debugEnSig,
  )
  if len(signals) != 1:
    raise ValueError("debug expression must contain exactly one hierarchical signal")
  return signals[0].rsplit('.', 1)[0]

def createZEROSanitizers(design, zeroSanitizerTemplates, debugEnSig\
                      , mode='jg', debug=False):

  design.zeroSanMetaData = {key: [] for key in zeroSanitizerTemplates.keys()}

  if (debugEnSig):
    zeroSanitizerType = 'clrOnDbg'
    debugOwner = debugSignalOwner(debugEnSig)
    for reg, regData in design.regList.items(): 
      if not reg.startswith(f"{debugOwner}."):
        continue
      sanitizerId = f"{zeroSanitizerType}_{design.numSanitizers:04d}"
      design.zeroSanMetaData[zeroSanitizerType].append({'clk': regData[1]\
                                               , 'debugEn': debugEnSig\
                                               , 'sig': reg\
                                               , 'stype': zeroSanitizerType\
                                               , 'id': sanitizerId\
                                                })
      design.numSanitizers+=1

  zeroSanitizerType = 'OneTimeZero'
  for targetIndex, target in enumerate(design.oneTimeRegs):
    packedTarget = f"zsan_packed_target_{targetIndex:04d}"
    targetDeclaration = (
        f"wire [$bits({target['tarSig']})-1:0] {packedTarget} = "
        f"{{>>{{{target['tarSig']}}}}};\n"
    )
    isFirstTargetSanitizer = True
    for interface in target['interfaces']:
      dataWidth = interface['data_width']
      for lowBit in range(0, target['width'], dataWidth):
        highBit = min(lowBit + dataWidth, target['width']) - 1
        targetSlice = f"{packedTarget}[{highBit}:{lowBit}]"
        chunkWidth = highBit - lowBit + 1
        targetWord = targetSlice
        if chunkWidth < dataWidth:
          targetWord = f"{{{dataWidth-chunkWidth}'b0, {targetSlice}}}"

        clearSignals = [(targetSlice, interface['clock'])]
        clearSignals += [
            (fanin['signal'], fanin['clock']) for fanin in target['fanin']
        ]
        for clearSignal, clock in clearSignals:
          sanitizerId = f"{zeroSanitizerType}_{design.numSanitizers:04d}"
          design.zeroSanMetaData[zeroSanitizerType].append({
              'clk': clock,
              'valid': interface['valid'],
              'targetWord': targetWord,
              'outputData': interface['data'],
              'clearSig': clearSignal,
              'stype': zeroSanitizerType,
              'id': sanitizerId,
              '_prefix': targetDeclaration if isFirstTargetSanitizer else '',
          })
          isFirstTargetSanitizer = False
          design.numSanitizers += 1
      

  sanitizerLines = []
  for zeroSanitizerType, templateValuesList in design.zeroSanMetaData.items():
    for templateValues in templateValuesList: 
      prefix = templateValues.get('_prefix', '')
      sanitizerLines.append(
          prefix
          + zeroSanitizerTemplates[zeroSanitizerType].substitute(**templateValues)
      )

  return sanitizerLines
