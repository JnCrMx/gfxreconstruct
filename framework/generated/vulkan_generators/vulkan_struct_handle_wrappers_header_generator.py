#!/usr/bin/python3 -i
#
# Copyright (c) 2019 Valve Corporation
# Copyright (c) 2019 LunarG, Inc.
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

import os,re,sys
from base_generator import *

class VulkanStructHandleWrappersHeaderGeneratorOptions(BaseGeneratorOptions):
    """Options for generating function prototypes to wrap Vulkan struct member handles at API capture"""
    def __init__(self,
                 blacklists = None,         # Path to JSON file listing apicalls and structs to ignore.
                 platformTypes = None,      # Path to JSON file listing platform (WIN32, X11, etc.) defined types.
                 filename = None,
                 directory = '.',
                 prefixText = '',
                 protectFile = False,
                 protectFeature = True):
        BaseGeneratorOptions.__init__(self, blacklists, platformTypes,
                                      filename, directory, prefixText,
                                      protectFile, protectFeature)

# VulkanStructHandleWrappersHeaderGenerator - subclass of BaseGenerator.
# Generates C++ function prototypes for wrapping struct member handles
# when recording Vulkan API call parameter data.
class VulkanStructHandleWrappersHeaderGenerator(BaseGenerator):
    """Generate C++ functions for Vulkan struct member handle wrapping at API capture"""
    def __init__(self,
                 errFile = sys.stderr,
                 warnFile = sys.stderr,
                 diagFile = sys.stdout):
        BaseGenerator.__init__(self,
                               processCmds=True, processStructs=True, featureBreak=False,
                               errFile=errFile, warnFile=warnFile, diagFile=diagFile)

        # Map of Vulkan structs containing handles to a list values for handle members or struct members
        # that contain handles (eg. VkGraphicsPipelineCreateInfo contains a VkPipelineShaderStageCreateInfo
        # member that contains handles).
        self.structsWithHandles = dict()
        self.outputStructs = []           # Output structures that retrieve handles, which need to be wrapped.

    # Method override
    def beginFile(self, genOpts):
        BaseGenerator.beginFile(self, genOpts)

        write('#include "encode/custom_vulkan_struct_handle_wrappers.h"', file=self.outFile)
        write('#include "encode/vulkan_handle_wrapper_util.h"', file=self.outFile)
        write('#include "format/platform_types.h"', file=self.outFile)
        write('#include "util/defines.h"', file=self.outFile)
        self.newline()
        write('#include "vulkan/vulkan.h"', file=self.outFile)
        self.newline()
        write('GFXRECON_BEGIN_NAMESPACE(gfxrecon)', file=self.outFile)
        write('GFXRECON_BEGIN_NAMESPACE(encode)', file=self.outFile)

    # Method override
    def endFile(self):
        self.newline()
        write('void UnwrapPNextStructHandles(const void* value, HandleStore* handle_store, HandleArrayStore* handle_array_store, HandleArrayUnwrapMemory* handle_unwrap_memory);', file=self.outFile)
        write('void RewrapPNextStructHandles(const void* value, HandleStore::const_iterator* handle_store_iter, HandleArrayStore::const_iterator* handle_array_store_iter);', file=self.outFile)
        self.newline()
        self.generateCreateWrapperFuncs()
        write('template <typename T>', file=self.outFile)
        write('void CreateWrappedStructArrayHandles(T* value, size_t len, PFN_GetHandleId get_id)', file=self.outFile)
        write('{', file=self.outFile)
        write('    if (value != nullptr)', file=self.outFile)
        write('    {', file=self.outFile)
        write('        for (size_t i = 0; i < len; ++i)', file=self.outFile)
        write('        {', file=self.outFile)
        write('            CreateWrappedStructHandles(&value[i], get_id);', file=self.outFile)
        write('        }', file=self.outFile)
        write('    }', file=self.outFile)
        write('}', file=self.outFile)
        self.newline()
        write('template <typename T>', file=self.outFile)
        write('void UnwrapStructArrayHandles(T* value, size_t len, HandleStore* handle_store, HandleArrayStore* handle_array_store, HandleArrayUnwrapMemory* handle_unwrap_memory)', file=self.outFile)
        write('{', file=self.outFile)
        write('    if (value != nullptr)', file=self.outFile)
        write('    {', file=self.outFile)
        write('        for (size_t i = 0; i < len; ++i)', file=self.outFile)
        write('        {', file=self.outFile)
        write('            UnwrapStructHandles(&value[i], handle_store, handle_array_store, handle_unwrap_memory);', file=self.outFile)
        write('        }', file=self.outFile)
        write('    }', file=self.outFile)
        write('}', file=self.outFile)
        self.newline()
        write('template <typename T>', file=self.outFile)
        write('void RewrapStructArrayHandles(T* value, size_t len, HandleStore::const_iterator* handle_store_iter, HandleArrayStore::const_iterator* handle_array_store_iter)', file=self.outFile)
        write('{', file=self.outFile)
        write('    if (value != nullptr)', file=self.outFile)
        write('    {', file=self.outFile)
        write('        for (size_t i = 0; i < len; ++i)', file=self.outFile)
        write('        {', file=self.outFile)
        write('            RewrapStructHandles(&value[i], handle_store_iter, handle_array_store_iter);', file=self.outFile)
        write('        }', file=self.outFile)
        write('    }', file=self.outFile)
        write('}', file=self.outFile)
        self.newline()
        write('GFXRECON_END_NAMESPACE(encode)', file=self.outFile)
        write('GFXRECON_END_NAMESPACE(gfxrecon)', file=self.outFile)

        # Finish processing in superclass
        BaseGenerator.endFile(self)

    #
    # Method override
    def genStruct(self, typeinfo, typename, alias):
        BaseGenerator.genStruct(self, typeinfo, typename, alias)

        if not alias:
            self.checkStructMemberHandles(typename, self.structsWithHandles)

    #
    # Indicates that the current feature has C++ code to generate.
    def needFeatureGeneration(self):
        if self.featureStructMembers or self.featureCmdParams:
            return True
        return False

    #
    # Performs C++ code generation for the feature.
    def generateFeature(self):
        # Check for output structures, which retrieve handles that need to be wrapped.
        for cmd in self.featureCmdParams:
            info = self.featureCmdParams[cmd]
            values = info[2]

            for value in values:
                if self.isOutputParameter(value) and self.isStruct(value.baseType) and (value.baseType in self.structsWithHandles) and (value.baseType not in self.outputStructs):
                    self.outputStructs.append(value.baseType)

        # Generate unwrap and rewrap code for input structures.
        for struct in self.getFilteredStructNames():
            if struct in self.structsWithHandles:
                body = '\n'
                body += 'void UnwrapStructHandles(const {}* value, HandleStore* handle_store, HandleArrayStore* handle_array_store, HandleArrayUnwrapMemory* handle_unwrap_memory);\n'.format(struct)
                body += 'void RewrapStructHandles(const {}* value, HandleStore::const_iterator* handle_store_iter, HandleArrayStore::const_iterator* handle_array_store_iter);'.format(struct)
                write(body, file=self.outFile)

    #
    # Generates functions that wrap struct handle members.
    def generateCreateWrapperFuncs(self):
        for struct in self.outputStructs:
            body = 'void CreateWrappedStructHandles({}* value, PFN_GetHandleId get_id);\n'.format(struct)
            write(body, file=self.outFile)
