class ValueParameter:

   TYPE = "ValueParameter"

   def __init__( self, name, value=None ):
      self.type = ValueParameter.TYPE
      self.name = name
      self.value = value

   def SetValue( self, value ):
      self.value = value

class RangeParameter( ValueParameter ):

   TYPE = "RangeParameter"

   def __init__( self, name, value, low, high ):
      ValueParameter.__init__( self, name, value )
      self.type = RangeParameter.TYPE
      self.low = low
      self.high = high

   def SetValue( self, value ):
      
      if self.low > value or self.high < value:
         raise ValueError("RangeParameter.SetValue")

      self.value = value

class OptionSetParameter( ValueParameter ): 

   TYPE = "OptionSetParameter"

   def __init__( self, name, value, options ):
      ValueParameter.__init__( self, name, value )
      self.type = OptionSetParameter.TYPE
      self.options = options

   def SetValue( self, value ):
      
      if value not in self.options:
         raise ValueError("OptionSetParameter.SetValue")

      self.value = value

def CreateParameter( parmstruct ):
   """
   Object factory to create parameter instances from those moronic SOAPStructs, 
   emphasizing that we should be using WSDL
   """
   if parmstruct.type == OptionSetParameter.TYPE:
      parameter = OptionSetParameter( parmstruct.name, parmstruct.value, parmstruct.options )
   elif parmstruct.type == RangeParameter.TYPE:
      parameter = RangeParameter( parmstruct.name, parmstruct.value, parmstruct.low, parmstruct.high )
   elif parmstruct.type == ValueParameter.TYPE:
      parameter = ValueParameter( parmstruct.name, parmstruct.value )

   return parameter