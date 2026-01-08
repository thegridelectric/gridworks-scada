<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform" xmlns:msxsl="urn:schemas-microsoft-com:xslt" exclude-result-prefixes="msxsl" xmlns:xs="http://www.w3.org/2001/XMLSchema">
    <xsl:output method="xml" indent="yes" />
    <xsl:param name="root" />
    <xsl:param name="codee-root" />
    <xsl:include href="../CommonXsltTemplates.xslt"/>
    <xsl:param name="exclude-collections" select="'false'" />
    <xsl:param name="relationship-suffix" select="''" />
    <xsl:variable name="airtable" select="/" />
    <xsl:variable name="squot">'</xsl:variable>
    <xsl:variable name="init-space">             </xsl:variable>
    <xsl:include href="GnfCommon.xslt"/>

    <xsl:template match="@*|node()">
        <xsl:copy>
            <xsl:apply-templates select="@*|node()" />
        </xsl:copy>
    </xsl:template>

    <xsl:template match="/">
        <FileSet>
            <FileSetFiles>
                <xsl:for-each select="$airtable//ProtocolTypes/ProtocolType[(normalize-space(ProtocolName) ='scada')]">
                <xsl:variable name="versioned-type-id" select="VersionedType"/>
                <xsl:for-each select="$airtable//VersionedTypes/VersionedType[(VersionedTypeId = $versioned-type-id)  and (Status = 'Active' or Status = 'Pending') and (ProtocolCategory= 'Json' or ProtocolCategory = 'GwAlgoSerial')]">
                <xsl:variable name="type-name" select="TypeName" />
                <xsl:variable name="total-attributes" select="count($airtable//TypeAttributes/TypeAttribute[(VersionedType = $versioned-type-id)])" />
                <xsl:variable name="versioned-type-name" select="VersionedTypeName"/>
                <xsl:variable name="python-class-name">
                    <xsl:if test="(normalize-space(PythonClassName) ='')">
                    <xsl:call-template name="nt-case">
                        <xsl:with-param name="type-name-text" select="TypeName" />
                    </xsl:call-template>
                    </xsl:if>
                    <xsl:if test="(normalize-space(PythonClassName) != '')">
                    <xsl:value-of select="normalize-space(PythonClassName)" />
                    </xsl:if>
                </xsl:variable>
                    <xsl:variable name="overwrite-mode">

                    <xsl:if test="not (Status = 'Pending')">
                    <xsl:text>Never</xsl:text>
                    </xsl:if>
                    <xsl:if test="(Status = 'Pending')">
                    <xsl:text>Always</xsl:text>
                    </xsl:if>
                    </xsl:variable>

                    <FileSetFile>
                                <xsl:element name="RelativePath"><xsl:text>../../../gw_spaceheat/named_types/</xsl:text>
                                <xsl:value-of select="translate($type-name,'.','_')"/><xsl:text>.py</xsl:text></xsl:element>

                        <OverwriteMode><xsl:value-of select="$overwrite-mode"/></OverwriteMode>
                        <xsl:element name="FileContents">


<xsl:text>"""Type </xsl:text><xsl:value-of select="$type-name"/><xsl:text>, version </xsl:text>
<xsl:value-of select="Version"/><xsl:text>"""

from typing import Any, Literal</xsl:text>
	<xsl:if test="count($airtable//TypeAttributes/TypeAttribute[(VersionedType = $versioned-type-id) and (IsList = 'true')])>0">
<xsl:text>, List</xsl:text>
</xsl:if>

<xsl:if test="count($airtable//TypeAttributes/TypeAttribute[(VersionedType = $versioned-type-id) and not (IsRequired = 'true')]) > 0">
<xsl:text>, Optional</xsl:text>
</xsl:if>


<xsl:variable name="use-field-validator" select="count($airtable//TypeAttributes/TypeAttribute[(VersionedType = $versioned-type-id) and
                            ((Axiom != '') or
                            (not (PrimitiveFormat = '') 
                                and PrimitiveFormat != 'UUID4Str'
                                and PrimitiveFormat != 'SpaceheatName' 
                                and PrimitiveFormat != 'LeftRightDot' 
                                and PrimitiveFormat != 'MarketSlotName' 
                                and PrimitiveFormat != 'HandleName'
                                and PrimitiveFormat != 'HexChar' 
                                and PrimitiveFormat != 'UTCSeconds' 
                                and PrimitiveFormat != 'UTCMilliseconds'
                                and PrimitiveFormat != 'PositiveInteger'
                               )
                            )
                            ]) > 0" />

<xsl:text>
from pydantic import BaseModel</xsl:text>

    
<xsl:if test="$use-field-validator='true'">
<xsl:text>, field_validator</xsl:text>
</xsl:if>
<xsl:if test="count($airtable//TypeAxioms/TypeAxiom[MultiPropertyAxiom=$versioned-type-id]) > 0 or count($airtable//TypeAttributes/TypeAttribute[(VersionedType = $versioned-type-id) and (IsEnum='true')]) > 0">
<xsl:text>, model_validator</xsl:text>
</xsl:if>
<xsl:if test="count($airtable//PropertyFormats/PropertyFormat[(normalize-space(Name) ='PositiveInteger')  and (count(TypesThatUse[text()=$versioned-type-id])>0)]) > 0">
<xsl:text>, PositiveInt</xsl:text>
</xsl:if>
<xsl:if test="ExtraAllowed='true'"><xsl:text>, ConfigDict</xsl:text>
</xsl:if>
<xsl:if test="count($airtable//TypeAttributes/TypeAttribute[(VersionedType = $versioned-type-id) 
                                and (PrimitiveType = 'Integer') 
                                and not(PropertyFormat = 'UTCMilliseconds') 
                                and not(PropertyFormat = 'UTCSeconds')
                                and not(PropertyFormat = 'PositiveInteger')
                                ])>0">
</xsl:if>


<xsl:if test="count($airtable//TypeAxioms/TypeAxiom[MultiPropertyAxiom=$versioned-type-id]) > 0">
<xsl:text>
from typing_extensions import Self</xsl:text>
</xsl:if>

<xsl:text>&#10;</xsl:text>
<xsl:if test="count(PropertyFormatsUsed)>0">
<xsl:for-each select="$airtable//PropertyFormats/PropertyFormat[(normalize-space(Name) ='MarketSlotNameLrdFormat')  and (count(TypesThatUse[text()=$versioned-type-id])>0)]">
<xsl:text>
from gw import check_is_market_slot_name_lrd_format</xsl:text>
</xsl:for-each>
</xsl:if>
<xsl:for-each select="$airtable//TypeAttributes/TypeAttribute[(VersionedType = $versioned-type-id)]">


<xsl:if test="(IsType = 'true') and (normalize-space(SubTypeDataClass) = '' or IsList = 'true')">
<xsl:text>
from gwsproto.named_types.</xsl:text>
<xsl:call-template name="python-case">
    <xsl:with-param name="camel-case-text" select="translate(SubTypeName,'.','_')"  />
</xsl:call-template>
<xsl:text> import </xsl:text>
<xsl:call-template name="nt-case">
    <xsl:with-param name="type-name-text" select="SubTypeName" />
</xsl:call-template>
</xsl:if>
</xsl:for-each>

<xsl:for-each select="$airtable//GtEnums//GtEnum[normalize-space(Name) !='']">
<xsl:sort select="Name" data-type="text"/>

<xsl:variable name="base-name" select="LocalName"/>
<xsl:variable name="enum-local-name">
<xsl:call-template name="nt-case">
    <xsl:with-param name="type-name-text" select="LocalName" />
</xsl:call-template>
</xsl:variable>
<xsl:if test="count($airtable//TypeAttributes/TypeAttribute[(VersionedType = $versioned-type-id) and (EnumLocalName[text() = $base-name])])>0">
<xsl:text>
from gwsproto.enums import </xsl:text>
<xsl:value-of select="$enum-local-name"/>
</xsl:if>
</xsl:for-each>


<xsl:if test="count(PropertyFormatsUsed)>0">
<xsl:for-each select="$airtable//PropertyFormats/PropertyFormat[(normalize-space(Name) ='AlgoAddressStringFormat')  and (count(TypesThatUse[text()=$versioned-type-id])>0)]">
<xsl:text>
import algosdk</xsl:text>
</xsl:for-each>

<xsl:text>
from gwsproto.property_format import (</xsl:text>
<xsl:for-each select="$airtable//PropertyFormats/PropertyFormat[(normalize-space(Name) !='')  and (count(TypesThatUse[text()=$versioned-type-id])>0)]">
<xsl:sort select="Name" data-type="text"/>
<xsl:choose>
<xsl:when test="normalize-space(Name) = 'UUID4Str'">
<xsl:text>
    UUID4Str,</xsl:text>
</xsl:when>
<xsl:when test="normalize-space(Name) = 'SpaceheatName'">
<xsl:text>
    SpaceheatName,</xsl:text>
</xsl:when>
<xsl:when test="normalize-space(Name) = 'LeftRightDot'">
<xsl:text>
    LeftRightDotStr,</xsl:text>
</xsl:when>
<xsl:when test="normalize-space(Name) = 'MarketSlotName'">
<xsl:text>
    MarketSlotName,</xsl:text>
</xsl:when>
<xsl:when test="normalize-space(Name) = 'HandleName'">
<xsl:text>
    HandleName,</xsl:text>
</xsl:when>
<xsl:when test="normalize-space(Name) = 'HexChar'">
<xsl:text>
    HexChar,</xsl:text>
</xsl:when>
<xsl:when test="normalize-space(Name) = 'UTCMilliseconds'">
<xsl:text>
    UTCMilliseconds,</xsl:text>
</xsl:when>
<xsl:when test="normalize-space(Name) = 'UTCSeconds'">
<xsl:text>
    UTCSeconds,</xsl:text>
</xsl:when>
<xsl:when test="normalize-space(Name) = 'PositiveInteger'">
<!-- Do nothing - this is tested by pydantic's PositiveInt -->
</xsl:when>
<xsl:otherwise>
<xsl:text>
    check_is_</xsl:text>
<xsl:call-template name="python-case">
    <xsl:with-param name="camel-case-text" select="translate(Name,'.','_')" />
</xsl:call-template>
    <xsl:text>,</xsl:text>
</xsl:otherwise>
</xsl:choose>
</xsl:for-each>
<xsl:text>
)</xsl:text>
</xsl:if>

<xsl:text>

class </xsl:text>
<xsl:value-of select="$python-class-name"/>
<xsl:text>(BaseModel):
    """
    </xsl:text>
    <!-- One line title, if it exists -->
    <xsl:if test="(normalize-space(Title) != '')">
        <xsl:value-of select="Title"/>
            <!-- With a space before the Description (if description exists)-->
            <xsl:if test="(normalize-space(Description) != '')">
                <xsl:text>.

    </xsl:text>
            </xsl:if>
    </xsl:if>

    <!-- Type Description, wrapped, if it exists -->
    <xsl:if test="(normalize-space(Description) != '')">
    <xsl:call-template name="wrap-text">
        <xsl:with-param name="text" select="normalize-space(concat(Description, ' ', UpdateDescription))"/>
        <xsl:with-param name="indent-spaces" select="4"/>
    </xsl:call-template>
    </xsl:if>


    <xsl:if test="(normalize-space(Url) != '')">
    <xsl:text>

    [More info](</xsl:text>
        <xsl:value-of select="normalize-space(Url)"/>
        <xsl:text>)</xsl:text>
    </xsl:if>
    <xsl:text>
    """
</xsl:text>


<xsl:for-each select="$airtable//TypeAttributes/TypeAttribute[(VersionedType = $versioned-type-id)]">
<xsl:sort select="Idx" data-type="number"/>

<xsl:variable name = "attribute-name">
        <xsl:value-of select="Value"/>
    <!-- If attribute is associated to a data class, add Id to the Attribute name-->
    <xsl:if test="not(normalize-space(SubTypeDataClass) = '') and not(IsList='true')">
    <xsl:text>Id</xsl:text>
    </xsl:if>
</xsl:variable>

<xsl:variable name="enum-local-name">
<xsl:call-template name="nt-case">
    <xsl:with-param name="type-name-text" select="EnumLocalName" />
</xsl:call-template>
</xsl:variable>

<xsl:variable name="attribute-type">

    <!-- If Optional, start the Optional bracket-->
    <xsl:if test="not(IsRequired = 'true')">
    <xsl:text>Optional[</xsl:text>
    </xsl:if>

    <!-- If List, start the List bracket-->
    <xsl:if test="IsList = 'true'">
    <xsl:text>List[</xsl:text>
    </xsl:if>
    <xsl:choose>
    <xsl:when test="(IsPrimitive = 'true')">

        <!--Some property formats have called-out names -->
        <xsl:choose>
        <xsl:when test="PrimitiveFormat = 'UUID4Str'">
        <xsl:text>UUID4Str</xsl:text>
        </xsl:when>
        <xsl:when test="PrimitiveFormat = 'SpaceheatName'">
        <xsl:text>SpaceheatName</xsl:text>
        </xsl:when>
        <xsl:when test="PrimitiveFormat = 'LeftRightDot'">
        <xsl:text>LeftRightDotStr</xsl:text>
        </xsl:when>
        <xsl:when test="PrimitiveFormat = 'MarketSlotName'">
        <xsl:text>MarketSlotName</xsl:text>
        </xsl:when>
        <xsl:when test="PrimitiveFormat = 'HandleName'">
        <xsl:text>HandleName</xsl:text>
        </xsl:when>
        <xsl:when test="PrimitiveFormat = 'HexChar'">
        <xsl:text>HexChar</xsl:text>
        </xsl:when>
        <xsl:when test="PrimitiveFormat = 'UTCMilliseconds'">
        <xsl:text>UTCMilliseconds</xsl:text>
        </xsl:when>
        <xsl:when test="PrimitiveFormat = 'UTCSeconds'">
        <xsl:text>UTCSeconds</xsl:text>
        </xsl:when>
        <xsl:when test="PrimitiveFormat = 'PositiveInteger'">
        <xsl:text>PositiveInt</xsl:text>
        </xsl:when>
        <xsl:when test="PrimitiveType='Integer'">
        <xsl:text>StrictInt</xsl:text>
        </xsl:when>
        <xsl:otherwise>
        <xsl:call-template name="python-type">
            <xsl:with-param name="gw-type" select="PrimitiveType"/>
        </xsl:call-template>
        </xsl:otherwise>
        </xsl:choose>
    </xsl:when>

    <xsl:when test = "(IsEnum = 'true')">
        <xsl:value-of select="$enum-local-name"/>
    </xsl:when>

    <!-- If Attribute is a type associated with a dataclass, the reference is to its id, which is a string -->
    <xsl:when test = "not(normalize-space(SubTypeDataClass) = '') and not(IsList = 'true')">
    <xsl:text>UUID4Str</xsl:text>
    </xsl:when>

    <!-- Otherwise, the reference is to the type  -->
    <xsl:when test="(IsType = 'true')">
        <xsl:call-template name="nt-case">
            <xsl:with-param name="type-name-text" select="SubTypeName" />
        </xsl:call-template>
    </xsl:when>
    <xsl:otherwise></xsl:otherwise>
    </xsl:choose>
            <!-- If List, end the List bracket-->
    <xsl:if test="IsList = 'true'">
    <xsl:text>]</xsl:text>
    </xsl:if>

    <!-- If Optional, end the Optional bracket-->
    <xsl:if test="not(IsRequired = 'true')">
    <xsl:text>] = None</xsl:text>
    </xsl:if>
</xsl:variable>

    <xsl:call-template name="insert-spaces"/>

     <!-- Name of the attribute -->
    <xsl:value-of select="$attribute-name"/><xsl:text>: </xsl:text>

    <!-- Add the attribute type (works for primitive, enum, subtype)-->
    <xsl:value-of select="$attribute-type"/>
    <xsl:text>&#10;</xsl:text>
<!-- End of declaring the attributes of the class-->
</xsl:for-each>


<xsl:text>    TypeName: Literal["</xsl:text><xsl:value-of select="TypeName"/><xsl:text>"] = "</xsl:text><xsl:value-of select="TypeName"/><xsl:text>"
    Version: Literal["</xsl:text>
<xsl:value-of select="Version"/><xsl:text>"] = "</xsl:text><xsl:value-of select="Version"/><xsl:text>"</xsl:text>

<xsl:if test="ExtraAllowed='true'"><xsl:text>

    model_config = ConfigDict(
        extra="allow"
    )</xsl:text>
</xsl:if>



<!-- CONSTRUCTING VALIDATORS CONSTRUCTING VALIDATORS  CONSTRUCTING VALIDATORS  CONSTRUCTING VALIDATORS  CONSTRUCTING VALIDATORS -->
<!-- CONSTRUCTING VALIDATORS CONSTRUCTING VALIDATORS  CONSTRUCTING VALIDATORS  CONSTRUCTING VALIDATORS  CONSTRUCTING VALIDATORS -->
<!-- CONSTRUCTING VALIDATORS CONSTRUCTING VALIDATORS  CONSTRUCTING VALIDATORS  CONSTRUCTING VALIDATORS  CONSTRUCTING VALIDATORS -->
<!-- CONSTRUCTING VALIDATORS CONSTRUCTING VALIDATORS  CONSTRUCTING VALIDATORS  CONSTRUCTING VALIDATORS  CONSTRUCTING VALIDATORS -->

    <xsl:for-each select="$airtable//TypeAttributes/TypeAttribute[(VersionedType = $versioned-type-id)]">
    <xsl:sort select="Idx" data-type="number"/>
    <xsl:variable name="type-attribute-id" select="TypeAttributeId" />

    <xsl:variable name="enum-local-name">
        <xsl:if test = "(IsEnum = 'true')">
            <xsl:call-template name="nt-case">
                            <xsl:with-param name="type-name-text" select="EnumLocalName" />
            </xsl:call-template>
        </xsl:if>
    </xsl:variable>

    <xsl:variable name="attribute-type">

        <!-- If Optional, start the Optional bracket-->
        <xsl:if test="not(IsRequired = 'true')">
        <xsl:text>Optional[</xsl:text>
        </xsl:if>

        <!-- If List, start the List bracket-->
        <xsl:if test="IsList = 'true'">
        <xsl:text>List[</xsl:text>
        </xsl:if>
        <xsl:choose>
        <xsl:when test="(IsPrimitive = 'true')">
        <xsl:call-template name="python-type">
            <xsl:with-param name="gw-type" select="PrimitiveType"/>
        </xsl:call-template>
        </xsl:when>

        <xsl:when test = "(IsEnum = 'true')">
            <xsl:value-of select="$enum-local-name"/>
        </xsl:when>

        <!-- If Attribute is a type associated with a dataclass, the reference is to its id, which is a string -->
        <xsl:when test = "not(normalize-space(SubTypeDataClass) = '')">
        <xsl:text>str</xsl:text>
        </xsl:when>

        <!-- Otherwise, the reference is to the type  -->
        <xsl:when test="(IsType = 'true')">
            <xsl:call-template name="nt-case">
                <xsl:with-param name="type-name-text" select="SubTypeName" />
            </xsl:call-template>
        </xsl:when>
        <xsl:otherwise></xsl:otherwise>
        </xsl:choose>
                <!-- If List, end the List bracket-->
        <xsl:if test="IsList = 'true'">
        <xsl:text>]</xsl:text>
        </xsl:if>

        <!-- If Optional, end the Optional bracket and a default of None-->
        <xsl:if test="not(IsRequired = 'true')">
        <xsl:text>]</xsl:text>
        </xsl:if>
    </xsl:variable>

    <xsl:variable name = "attribute-name">
            <xsl:value-of select="Value"/>
        <!-- If attribute is associated to a data class, add Id to the Attribute name-->
        <xsl:if test="not(normalize-space(SubTypeDataClass) = '') and not(IsList='true')">
        <xsl:text>Id</xsl:text>
        </xsl:if>
    </xsl:variable>

    <xsl:if test="((Axiom != '') or
                            (not (PrimitiveFormat = '') 
                                and PrimitiveFormat != 'UUID4Str'
                                and PrimitiveFormat != 'SpaceheatName' 
                                and PrimitiveFormat != 'LeftRightDot'
                                and PrimitiveFormat != 'MarketSlotName' 
                                and PrimitiveFormat != 'HandleName' 
                                and PrimitiveFormat != 'HexChar' 
                                and PrimitiveFormat != 'UTCSeconds' 
                                and PrimitiveFormat != 'UTCMilliseconds'
                                and PrimitiveFormat != 'PositiveInteger'
                               )
                            )">
    <xsl:text>

    @field_validator("</xsl:text><xsl:value-of select="$attribute-name"/><xsl:text>"</xsl:text>

    <xsl:if test="PreValidateFormat='true'">
    <xsl:text>, mode="before"</xsl:text>
    </xsl:if>
    <xsl:text>)
    @classmethod
    def </xsl:text>

    <!-- add an underscore if there are no axioms getting checked, in which case its just property formats and/or enums -->
    <xsl:if test="count($airtable//TypeAxioms/TypeAxiom[(normalize-space(SinglePropertyAxiom)=$type-attribute-id)]) = 0">
    <xsl:text>_</xsl:text>
    </xsl:if>

    <xsl:text>check_</xsl:text><xsl:call-template name="python-case">
        <xsl:with-param name="camel-case-text" select="$attribute-name"  />
        </xsl:call-template><xsl:text>(cls, v: </xsl:text>
        <xsl:value-of select="$attribute-type"/>
        <xsl:text>) -> </xsl:text>
        <xsl:value-of select="$attribute-type"/>
        <xsl:text>:</xsl:text>

        <xsl:if test="count($airtable//TypeAxioms/TypeAxiom[(normalize-space(SinglePropertyAxiom)=$type-attribute-id)]) > 1">
        <xsl:text>
        """
        Axioms </xsl:text>
        <xsl:for-each select="$airtable//TypeAxioms/TypeAxiom[(normalize-space(SinglePropertyAxiom)=$type-attribute-id)]">
        <xsl:sort select="AxiomNumber" data-type="number"/>
        <xsl:value-of select="AxiomNumber"/>
                <xsl:if test="position() != count($airtable//TypeAxioms/TypeAxiom[(normalize-space(SinglePropertyAxiom)=$type-attribute-id)])">
                <xsl:text>, </xsl:text>
                </xsl:if>
        </xsl:for-each>
        <xsl:text>:</xsl:text>
        </xsl:if>

        <xsl:if test="count($airtable//TypeAxioms/TypeAxiom[(normalize-space(SinglePropertyAxiom)=$type-attribute-id)]) = 1">
        <xsl:text>
        """</xsl:text>
        </xsl:if>

        <xsl:if test="count($airtable//TypeAxioms/TypeAxiom[(normalize-space(SinglePropertyAxiom)=$type-attribute-id)]) > 0">
        <xsl:for-each select="$airtable//TypeAxioms/TypeAxiom[(normalize-space(SinglePropertyAxiom)=$type-attribute-id)]">
        <xsl:sort select="AxiomNumber" data-type="number"/>

        <xsl:if test="count($airtable//TypeAxioms/TypeAxiom[(normalize-space(SinglePropertyAxiom)=$type-attribute-id)]) =1">
        <xsl:text>
        Axiom </xsl:text>
        </xsl:if>

        <xsl:if test="count($airtable//TypeAxioms/TypeAxiom[(normalize-space(SinglePropertyAxiom)=$type-attribute-id)]) >1">
        <xsl:text>

        Axiom </xsl:text>
        </xsl:if>

        <xsl:value-of select="AxiomNumber"/><xsl:text>: </xsl:text>
        <xsl:value-of select="Title"/>

        <xsl:if test="normalize-space(Description)!=''">
        <xsl:text>.
        </xsl:text>
         <xsl:call-template name="wrap-text">
        <xsl:with-param name="text" select="normalize-space(Description)"/>
        </xsl:call-template>
        </xsl:if>
        <xsl:if test="normalize-space(Url)!=''">
        <xsl:text>
        [More info](</xsl:text><xsl:value-of select="Url"/>
        <xsl:text>)</xsl:text>

        </xsl:if>

        </xsl:for-each>
        <xsl:text>
        """</xsl:text>
        </xsl:if>



        <xsl:if test="not(IsRequired = 'true')">
                <xsl:text>
        if v is None:
            return v</xsl:text>
        </xsl:if>

        <xsl:if test="count($airtable//TypeAxioms/TypeAxiom[(normalize-space(SinglePropertyAxiom)=$type-attribute-id)]) > 0">
        <xsl:text>
        # Implement Axiom(s)</xsl:text>
        </xsl:if>

        <xsl:choose>

        <!-- Format needs validating; not a list-->
        <xsl:when test="PrimitiveFormat !='' 
                        and PrimitiveFormat != 'UUID4Str' 
                        and PrimitiveFormat != 'SpaceheatName' 
                        and PrimitiveFormat != 'LeftRightDot' 
                        and PrimitiveFormat != 'MarketSlotName' 
                        and PrimitiveFormat != 'HandleName' 
                        and PrimitiveFormat != 'HexChar' 
                        and PrimitiveFormat != 'UTCMilliseconds' 
                        and PrimitiveFormat != 'UTCSeconds' 
                        and PrimitiveFormat != 'PositiveInteger' 
                        and not(IsList='true')">
        <xsl:text>
        try:
            check_is_</xsl:text>
            <xsl:call-template name="python-case">
                <xsl:with-param name="camel-case-text" select="translate(PrimitiveFormat,'.','_')"  />
                </xsl:call-template>
        <xsl:text>(v)
        except ValueError as e:</xsl:text>
        <xsl:choose>
            <xsl:when test="string-length(PrimitiveFormat) + string-length(Value)> 24">
            <xsl:text>
            raise ValueError(
                f"</xsl:text><xsl:value-of select="Value"/><xsl:text> failed </xsl:text>
            <xsl:value-of select="PrimitiveFormat"/>
            <xsl:text> format validation: {e}",
            ) from e</xsl:text>
            </xsl:when>
            <xsl:otherwise>
            <xsl:text>
            raise ValueError(f"</xsl:text><xsl:value-of select="Value"/><xsl:text> failed </xsl:text>
            <xsl:value-of select="PrimitiveFormat"/>
            <xsl:text> format validation: {e}") from e</xsl:text>
            </xsl:otherwise>
        </xsl:choose>
        </xsl:when>

        <!-- Format needs validating; is a list-->
        <xsl:when test="PrimitiveFormat !='' 
                        and PrimitiveFormat != 'UUID4Str' 
                        and PrimitiveFormat != 'SpaceheatName' 
                        and PrimitiveFormat != 'LeftRightDot' 
                        and PrimitiveFormat != 'MarketSlotName' 
                        and PrimitiveFormat != 'HandleName' 
                        and PrimitiveFormat != 'HexChar' 
                        and PrimitiveFormat != 'UTCMilliseconds' 
                        and PrimitiveFormat != 'UTCSeconds'
                        and PrimitiveFormat != 'PositiveInteger'
                        and (IsList='true')">
        <xsl:text>
        try:
            for elt in v:
                check_is_</xsl:text>
            <xsl:call-template name="python-case">
                <xsl:with-param name="camel-case-text" select="translate(PrimitiveFormat,'.','_')"  />
            </xsl:call-template>
        <xsl:text>(elt)
        except ValueError as e:
            raise ValueError(
                f"</xsl:text><xsl:value-of select="Value"/><xsl:text> element failed </xsl:text>
            <xsl:value-of select="PrimitiveFormat" />
            <xsl:text> format validation: {e}",
            ) from e</xsl:text>
        </xsl:when>

         <!-- SubType w Data Class; not a list-->
        <xsl:when test = "not(normalize-space(SubTypeDataClass) = '') and not(IsList='true')">
        <xsl:text>
        try:
            is_uuid4_str(v)
        except ValueError as e:
            raise ValueError(
                f"</xsl:text>
                <xsl:value-of select="Value"/><xsl:text>Id failed UUID4Str format validation: {e}",
            ) from e</xsl:text>
        </xsl:when>

         <!-- SubType w Data Class; is a list-->
        <xsl:when test="not(normalize-space(SubTypeDataClass) = '') and IsList='true'">
        <xsl:text>
        try:
            for elt in v:
                is_uuid4_str(elt)
        except ValueError as e:
            raise ValueError(
                f"</xsl:text><xsl:value-of select="Value"/><xsl:text> element failed </xsl:text>
            <xsl:value-of select="PrimitiveFormat" />
            <xsl:text> format validation: {e}",
            ) from e</xsl:text>
        </xsl:when>

        <xsl:otherwise>
        </xsl:otherwise>
        </xsl:choose>

    </xsl:if>
    <!-- End the field_validator by returning v-->
    <xsl:if test="(not(PrimitiveFormat = '') 
                and PrimitiveFormat != 'UUID4Str' 
                and PrimitiveFormat != 'SpaceheatName' 
                and PrimitiveFormat != 'LeftRightDot' 
                and PrimitiveFormat != 'MarketSlotName' 
                and PrimitiveFormat != 'HandleName' 
                and PrimitiveFormat != 'HexChar' 
                and PrimitiveFormat != 'UTCSeconds' 
                and PrimitiveFormat != 'UTCMilliseconds'
                and PrimitiveFormat != 'PositiveInteger'
                ) 
                or (Axiom != '')">
        <xsl:text>
        return v</xsl:text>
    </xsl:if>
    
        </xsl:for-each>



    <xsl:if test="count($airtable//TypeAxioms/TypeAxiom[MultiPropertyAxiom=$versioned-type-id]) > 0">
    <xsl:for-each select="$airtable//TypeAxioms/TypeAxiom[MultiPropertyAxiom=$versioned-type-id]">
    <xsl:sort select="AxiomNumber" data-type="number"/>
    <xsl:text>

    @model_validator</xsl:text>
    <xsl:if test="CheckFirst='true'">
     <xsl:text>(mode="before")</xsl:text>
    </xsl:if>
    <xsl:if test="not(CheckFirst='true')">
     <xsl:text>(mode="after")</xsl:text>
    </xsl:if>
    <xsl:text>
    def check_axiom_</xsl:text><xsl:value-of select="AxiomNumber"/><xsl:text>(self) -> Self:
        """
        Axiom </xsl:text><xsl:value-of select="AxiomNumber"/><xsl:text>: </xsl:text>
        <xsl:value-of select="Title"/>
        <xsl:text>.
        </xsl:text><xsl:value-of select="Description"/>
        <xsl:if test="normalize-space(Url)!=''">
        <xsl:text>
        [More info](</xsl:text>
        <xsl:value-of select="normalize-space(Url)"/>
        <xsl:text>)</xsl:text>
        </xsl:if>

        <xsl:text>
        """
        # Implement check for axiom </xsl:text><xsl:value-of select="AxiomNumber"/><xsl:text>"
        return self</xsl:text>

    </xsl:for-each>
    </xsl:if>



<!-- Add newline at EOF for git and pre-commit-->
<xsl:text>&#10;</xsl:text>

                        </xsl:element>
                     </FileSetFile>
                </xsl:for-each>
                </xsl:for-each>
            </FileSetFiles>
        </FileSet>
    </xsl:template>


</xsl:stylesheet>
