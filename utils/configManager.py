"""
- This file uses a automated way of providing arguments to the script
    - The argument values can be edited either from the config file or the terminal command
"""

import json, os, argparse, re, pprint
import types


defaultKeysInConfigFileDict = ['__builtins__', '__cached__', '__doc__'\
                             , '__file__', '__loader__', '__name__'\
                             , '__package__', '__spec__']

def printConfig(input_config): 
    print_string = ""
    for key, data in input_config.__dict__.items():
        if key in defaultKeysInConfigFileDict:  # we dont want to print default stuff
            continue

        prettyPrintString = pprint.PrettyPrinter(indent=2).pformat(data)
        print_string = ''.join([print_string, f"\n {key} : {prettyPrintString}"])

    return print_string


"""
This func takes the imported config file module as input and converts into 
a dict with the variable names
"""
def getConfigFileDict(configFile):
    
    # convert the config file module to dict
    configFileDict = configFile.__dict__

    # check to make sure there are no more default keys
    for key in configFileDict.keys():
        assert (key in defaultKeysInConfigFileDict or '__' not in key), f"new default key may be present in config file, {key} {defaultKeysInConfigFileDict}"

    #print(configFile)
    #pp = pprint.PrettyPrinter(indent=4)
    #pp.pprint(configFile.__dict__)
    
    return configFileDict


"""
This function sets up all arguments to argparse using variables from config file
dict,  if a user does not input any arguments, then default value from config 
file is used
"""
def setupArgparse(configFileDict):

    assert "argVars" in configFileDict.keys(), f"couldnt find argVars variable in config file, {configFileDict.keys()}"
    argVars = configFileDict["argVars"]

    parser = argparse.ArgumentParser(description='choose the arguments')

    for key, data in argVars.items():
        arg_data = {}
        arg_data["required"] = False
        arg_data["default"] = data["v"]

        # if the type is list, we need to handle it carefully
        if type(data["v"]) == type([1,1]): # [1,1] here is just an example of list
            arg_data["nargs"] = '+'
            if data["v"]:
                arg_data["type"] = type(data["v"][0])
            elif data["c"]:
                arg_data["type"] = type(data["c"][0])
            else:
                arg_data["type"] = str
        else: 
            arg_data["type"] = type(data["v"])

        if data['c']: 
            # make sure the default value we are using from config file is within
            # the valid choices
            if type(data["v"]) == type([1,1]):
                assert all(value in data["c"] for value in data["v"]), \
                    f"invalid value: {data['v']} for {key} in config file. choices={data['c']}"
            else:
                assert data["v"] in data["c"], f"invalid value: {data['v']} for {key} in config file. choices={data['c']}" 
            arg_data["choices"] = data["c"]

        if data['h']: 
            arg_data["help"] = data["h"]

        parser.add_argument(f"-{data['s']}", f"--{key}", **arg_data)

    return parser


"""
Creates variables in config with ones frm argvars, take the values from argparse
Note that if any variable is not present as input argument, then the default 
value frm config file is auto set by the argparse 
"""
def updateConfigFileDict(configFileDict, parser):

    inputArgs = parser.parse_args()
    inputArgsDict = inputArgs.__dict__

    configArgs = configFileDict["argVars"]

    for key, data in configArgs.items():
        configFileDict[key] = inputArgsDict[key] 

    return configFileDict


"""
This func creates variables in config frm funcs, the values are derived 
with new variable values updated from input args
"""
def updateFuncsConfigFileDict(configFileDict):

    for key, data in configFileDict.items():
        if key in defaultKeysInConfigFileDict:  # dont touch default stuff in config class
            continue
        if isinstance(data, types.FunctionType):
            #print(key)
            configFileDict[key] = configFileDict[key]()

    return configFileDict


"""
"""
def convertConfigDictToObject(configFileDict): 
    
    CONFIG = Struct(**configFileDict)

    return CONFIG


"""
This function first extract all the config variables declared in the config file,
sets up argparse to allow all variables to be configured as arguments, &
updates config variables with the arguments from argparse. 
"""
def getCONFIG(configInfo, configType='file'):

    # get all the variables in the config file/dict as a dict
    if configType == 'file': 
        configFileDict = getConfigFileDict(configInfo)
    elif configType == 'dict': 
        configFileDict = configInfo 
    else: 
        assert 0, f"incorrect configtype, {configType}"


    # setup argparse using variables from the "arg" dict of config file
    parser = setupArgparse(configFileDict)

    # update the config dict with values from input arguments
    configFileDict = updateConfigFileDict(configFileDict, parser)

    # update the values that depend on other values in config file
    configFileDict = updateFuncsConfigFileDict(configFileDict)

    # add a func for pretty printing: 
    configInfo.printConfig = printConfig

    return configInfo
