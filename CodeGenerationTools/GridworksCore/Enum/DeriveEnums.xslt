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
                <xsl:for-each select="$airtable//ProtocolEnums/ProtocolEnum[(normalize-space(ProtocolName) ='scada') and not (NoVersions = 'true')]">
                <xsl:variable name="enum-id" select="GtEnumId"/>
                <xsl:variable name="enum-version" select="EnumVersion"/>
                <xsl:variable name="enum-name" select="EnumName"/>
                <xsl:variable name="local-name" select="LocalName"/>
                <xsl:for-each select="$airtable//GtEnums/GtEnum[GtEnumId=$enum-id]">
                    <xsl:variable name="enum-type" select="EnumType" />
                    <xsl:variable name="enum-class-name">
                        <xsl:call-template name="nt-case">
                            <xsl:with-param name="type-name-text" select="LocalName" />
                        </xsl:call-template>
                    </xsl:variable>
                    <FileSetFile>
                                <xsl:element name="RelativePath"><xsl:text>../../../gw_spaceheat/enums/</xsl:text>
                                <xsl:value-of select="translate(LocalName,'.','_')"/><xsl:text>.py</xsl:text></xsl:element>

                        <OverwriteMode>Always</OverwriteMode>
                        <xsl:element name="FileContents">


<xsl:text>from enum import auto
from typing import List

from gwsproto.enums.gw_str_enum import AslEnum


class </xsl:text><xsl:value-of select="$enum-class-name"/>
<xsl:text>(AslEnum):
    """
    </xsl:text>
    <!-- Enum description, wrapped, if it exists -->
    <xsl:if test="(normalize-space(Description) != '')">
    <xsl:call-template name="wrap-text">
        <xsl:with-param name="text" select="normalize-space(Description)"/>
        <xsl:with-param name="indent-spaces" select="4"/>
    </xsl:call-template>
    </xsl:if>
    <xsl:text>
    Values:</xsl:text>
    <xsl:for-each select="$airtable//EnumSymbols/EnumSymbol[(Enum = $enum-id)  and (Version &lt;= $enum-version)]">
    <xsl:sort select="Idx" data-type="number"/>
    <xsl:text>
      - </xsl:text>
      <xsl:value-of select="LocalValue"/>

    <xsl:if test="(normalize-space(Description)!='') or (normalize-space(Url)!='')">
    <xsl:text>: </xsl:text>
    </xsl:if>
    <xsl:variable name="first-line-indent">
        <xsl:value-of select="8 + string-length(LocalValue)" />
    </xsl:variable>

    <xsl:call-template name="wrap-text">
        <xsl:with-param name="text" select="normalize-space(Description)" />
        <xsl:with-param name="indent-spaces" select="8"/>
        <xsl:with-param name="first-line-shorter-by" select="$first-line-indent"/>
     </xsl:call-template>

    <xsl:if test="(normalize-space(Url)!='')">
    <xsl:text> [More Info](</xsl:text>
    <xsl:value-of select="normalize-space(Url)"/>
    <xsl:text>).</xsl:text>
    </xsl:if>

    </xsl:for-each>
    <xsl:text>

    For more information:
      - [ASLs](https://gridworks-type-registry.readthedocs.io/en/latest/)
      - [Global Authority](https://gridworks-type-registry.readthedocs.io/en/latest/enums.html#</xsl:text>
    <xsl:value-of select="translate($enum-name,'.','')"/>
    <xsl:text>)</xsl:text>

    <xsl:if test="(normalize-space(Url)!='')">
    <xsl:text>
      - [More Info](</xsl:text>
    <xsl:value-of select="normalize-space(Url)"/>
    <xsl:text>)</xsl:text>
    </xsl:if>
    <xsl:text>
    """

</xsl:text>

<xsl:for-each select="$airtable//EnumSymbols/EnumSymbol[(Enum = $enum-id)  and (Version &lt;= $enum-version)]">
<xsl:sort select="Idx" data-type="number"/>
 <xsl:call-template name="insert-spaces">
    <xsl:with-param name="count" select="4"/>
</xsl:call-template>
<xsl:if test="$enum-type = 'Upper'">
    <xsl:value-of select="translate(translate(LocalValue,'-',''),$lcletters, $ucletters)"/>
</xsl:if>
<xsl:if test="$enum-type ='UpperPython'">
    <xsl:value-of select="LocalValue"/>
</xsl:if>

<xsl:text> = auto()
</xsl:text>
</xsl:for-each>
<xsl:text>
    @classmethod
    def default(cls) -> "</xsl:text>
    <xsl:value-of select="$enum-class-name"/>
    <xsl:text>":
        return cls.</xsl:text>
        <xsl:if test="$enum-type = 'Upper'">
            <xsl:value-of select="translate(translate(DefaultEnumValue,'-',''),$lcletters, $ucletters)"/>
        </xsl:if>
        <xsl:if test="$enum-type ='UpperPython'">
            <xsl:value-of select="DefaultEnumValue"/>
        </xsl:if>

    <xsl:text>

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "</xsl:text>
    <xsl:value-of select="$enum-name"/>
    <xsl:text>"

    @classmethod
    def enum_version(cls) -> str:
        return "</xsl:text>
    <xsl:value-of select="$enum-version"/>
    <xsl:text>"</xsl:text>



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
