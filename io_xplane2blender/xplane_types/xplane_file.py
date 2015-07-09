# File: xplane_file.py
# Defines X-Plane file data type.

import bpy
from .xplane_bone import XPlaneBone
from .xplane_light import XPlaneLight
# from .xplane_line import XPlaneLine
# from .xplane_object import XPlaneObject
from .xplane_primitive import XPlanePrimitive
from .xplane_lights import XPlaneLights
from .xplane_mesh import XPlaneMesh
from .xplane_header import XPlaneHeader
from ..xplane_config import getDebug, getDebugger, version

# Function: getActiveLayers
# Returns indices of all active Blender layers.
#
# Returns:
#   list - Indices of all active blender layers.
def getActiveBlenderLayerIndexes():
    layers = []
    for i in range(0,len(bpy.context.scene.layers)):
        if bpy.context.scene.layers[i] and bpy.context.scene.xplane.layers[i].export:
            layers.append(i)

    return layers

def getXPlaneLayerForBlenderLayerIndex(layerIndex):
    if len(bpy.context.scene.xplane.layers) > 0:
        return bpy.context.scene.xplane.layers[layerIndex]
    else:
        return None

def getFilenameFromXPlaneLayer(xplaneLayer):
    if xplaneLayer.name == "":
        filename = "layer_%s" % (str(xplaneLayer.index+1).zfill(2))
    else:
        filename = xplaneLayer.name

    return filename

def createFilesFromBlenderLayers():
    files = []

    for layerIndex in getActiveBlenderLayerIndexes():
        xplaneFile = createFileFromBlenderLayerIndex(layerIndex)
        if xplaneFile:
            files.append(xplaneFile)


def createFileFromBlenderLayerIndex(layerIndex):
    xplaneFile = None
    xplaneLayer = getXPlaneLayerForBlenderLayerIndex(layerIndex)

    if xplaneLayer:
        xplaneFile = XPlaneFile(getFilenameFromXPlaneLayer(xplaneLayer), xplaneLayer)

        if xplaneFile:
            xplaneFile.collectFromBlenderLayerIndex(layerIndex)

    return xplaneFile

# Class: XPlaneFile
# X-Plane OBJ file
class XPlaneFile():

    def __init__(self, filename, options):
        self.filename = filename

        self.options = options

        self.mesh = XPlaneMesh()

        self.lights = XPlaneLights()

        self.header = XPlaneHeader(self, 8)

        # list of temporary objects that will be removed after export
        self.tempBlenderObjects = []

        # dict of xplane objects within the file
        self.objects = {}

        # the root bone: origin for all animations/objects
        self.rootBone = XPlaneBone()

    # Method: collectFromBlenderLayerIndex
    # collects all objects in a given blender layer
    #
    # Parameters:
    #   layerIndex - int
    def collectFromBlenderLayerIndex(self, layerIndex):
        debug = getDebug()
        debugger = getDebugger()

        currentFrame = bpy.context.scene.frame_current

        blenderObjects = []

        for blenderObject in bpy.context.scene.objects:
            for i in range(len(blenderObject.layers)):
                if debug:
                    debugger.debug("scanning %s" % blenderObject.name)

                if blenderObject.layers[i] == True and i == layerIndex and blenderObject.hide == False:
                    blenderObjects.append(blenderObject)

        self.collectBlenderObjects(blenderObjects)
        self.collectBonesFromBlenderObjects(self.rootBone, blenderObjects)

        # restore frame before export
        bpy.context.scene.frame_set(frame = currentFrame)

    def collectBlenderObjects(self, blenderObjects):
        for blenderObject in blenderObjects:
            xplaneObject = self.convertBlenderObject(blenderObject)

            if xplaneObject:
                if isinstance(xplaneObject, XPlaneLight):
                    # attach xplane light to lights list
                    self.lights.append(xplaneObject)

                # store xplane object under same name as blender object in dict
                self.objects[blenderObject.name] = xplaneObject

    # collects all child bones for a given parent bone given a list of blender objects
    def collectBonesFromBlenderObjects(self, parentBone, blenderObjects, needsFilter = True):
        parentBlenderObject = parentBone.blenderObject

        def objectFilter(blenderObject):
            if parentBlenderObject:
                return blenderObject.parent == parentBlenderObject
            else:
                return blenderObject.parent == None

        # filter out all objects with given parent
        if needsFilter:
            blenderObjects = filter(objectFilter, blenderObjects)

        for blenderObject in blenderObjects:
            xplaneObject = None
            if blenderObject.name in self.objects:
                xplaneObject = self.objects[blenderObject.name]

            bone = XPlaneBone(blenderObject, xplaneObject, parentBone)
            parentBone.children.append(bone)

            bone.collectAnimations()

            if blenderObject.type == 'ARMATURE':
                self.collectBonesFromBlenderBones(bone, blenderObject, blenderObject.data.bones)
            else:
                self.collectBonesFromBlenderObjects(bone, blenderObject.children, False)

    def collectBonesFromBlenderBones(self, parentBone, blenderArmature, blenderBones, needsFilter = True):
        parentBlenderBone = parentBone.blenderBone

        def boneFilter(blenderBone):
            if parentBlenderBone:
                return blenderBone.parent == parentBlenderBone
            else:
                return blenderBone.parent == None

        # filter out all objects with given parent
        if needsFilter:
            blenderBones = filter(boneFilter, blenderBones)

        for blenderBone in blenderBones:
            bone = XPlaneBone(blenderArmature, None, parentBone)
            bone.blenderBone = blenderBone
            parentBone.children.append(bone)

            bone.collectAnimations()

            # collect child blender objects of this bone
            childBlenderObjects = self.getChildBlenderObjectsForBlenderBone(blenderBone)

            self.collectBonesFromBlenderObjects(bone, childBlenderObjects, False)
            self.collectBonesFromBlenderBones(bone, blenderArmature, blenderBone.children, False)

    def getChildBlenderObjectsForBlenderBone(self, blenderBone):
        blenderObjects = []

        for name in self.objects:
            xplaneObject = self.objects[name]
            if xplaneObject.blenderObject.parent_bone == blenderBone.name:
                blenderObjects.append(xplaneObject.blenderObject)

        return blenderObjects

    # Method: collectFromBlenderRootObject
    # collects all objects in a given blender root object
    #
    # Parameters:
    #   rootObject - blender object
    def collectFromBlenderRootObject(self, rootObject):
        currentFrame = bpy.context.scene.frame_current

        # TODO: do stuff

        # restore frame before export
        bpy.context.scene.frame_set(frame = currentFrame)

    # Method: convertBlenderObject
    # Converts/wraps blender object into an <XPlaneObject> or subtype
    #
    # Returns:
    #   <XPlaneObject> or None if object type is not supported
    def convertBlenderObject(self, blenderObject):
        debug = getDebug()
        debugger = getDebugger()

        xplaneObject = None

        # mesh: let's create a prim out of it
        if blenderObject.type == "MESH":
            if debug:
                debugger.debug("\t %s: adding to list" % blenderObject.name)
            xplaneObject = XPlanePrimitive(blenderObject)

        # lamp: let's create a XPlaneLight. Those cannot have children (yet).
        elif blenderObject.type == "LAMP":
            if debug:
                debugger.debug("\t %s: adding to list" % blenderObject.name)
            xplaneObject  = XPlaneLight(blenderObject)

        return xplaneObject

    def getBoneByBlenderName(self, name, parent = None):
        if not parent:
            parent = self.rootBone

        for bone in parent.children:
            if bone.getBlenderName() == name:
                return bone
            else: # decsent to children
                _bone = self.getBoneByBlenderName(name, bone)
                if _bone:
                    return _bone

        return None

    # Method: getObjectsList
    # Returns objects as a list
    def getObjectsList(self):
        objects = []
        for name in self.objects:
            objects.append(self.objects[name])

        return objects

    def writeFooter(self):
        build = 'unknown'

        if hasattr(bpy.app, 'build_hash'):
            build = bpy.app.build_hash
        else:
            build = bpy.app.build_revision

        return "# Build with Blender %s (build %s) Exported with XPlane2Blender %d.%d.%d" % (bpy.app.version_string,build, version[0], version[1], version[2])

    # Method: write
    # Returns OBJ file code
    def write(self):
        self.mesh.collectXPlaneObjects(self.getObjectsList())

        o = ''
        o += self.header.write()
        o += '\n'
        o += self.mesh.write()

        o += '\n'
        o += self.lights.write()

        o += '\n'
        o += self.writeFooter()        

        return o

    # Method: cleanup
    # Removes temporary blender data
    def cleanup(self):
        while(len(self.tempBlenderObjects) > 0):
            tempBlenderObject = self.tempBlenderObjects.pop()
            bpy.data.objects.remove(tempBlenderObject)