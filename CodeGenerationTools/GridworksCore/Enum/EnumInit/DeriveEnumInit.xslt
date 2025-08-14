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

            <FileSetFile>
                    <xsl:element name="RelativePath"><xsl:text>../../../../gw_spaceheat/enums/__init__.py</xsl:text></xsl:element>

                <OverwriteMode>Always</OverwriteMode>
                <xsl:element name="FileContents">
<xsl:text>"""
GridWorks Enums used in Application Shared Languages (ASL)

GridWorks ASL enables peer-to-peer shared vocabulary between energy system actors like 
SCADA devices, trading nodes, and market makers. Enums serve as the "controlled vocabulary" 
foundation that ensures everyone speaks the same language.

Key characteristics:
 - Immutable evolution: Enum values can be added but never changed or removed, ensuring 
   backwards compatibility across distributed systems
 - Transport-agnostic: Same enums work with RabbitMQ, HTTP APIs, Kafka, or any message delivery
 - Organizational autonomy: Each organization can build exactly the sophistication they need
   on top of shared foundations
 - Constitutional governance: Follow naming conventions (left.right.dot format) and 
   ownership rules defined in the ASL registry

Enums are the semantic building blocks that enable organizations to collaborate without 
compromising their independence. Unlike APIs where one party controls the vocabulary, 
ASL enums evolve through community governance while maintaining stability.

Application Shared Languages represent an evolution beyond traditional APIs - enabling 
true peer-to-peer collaboration where organizations maintain autonomy while sharing 
vocabulary, rather than client/server relationships where one party dictates the interface.

For more information:
 - [Why GridWorks ASL Exists](https://gridworks-asl.readthedocs.io/motivation/)
 - [ASL Rules and Guidelines](https://gridworks-asl.readthedocs.io/rules-and-guidelines/) 
 - [GridWorks ASL Overview](https://gridworks-asl.readthedocs.io/)
 """

from gw.enums import MarketTypeName</xsl:text>
<xsl:for-each select="$airtable//ProtocolEnums/ProtocolEnum[(normalize-space(ProtocolName) ='scada') and not(normalize-space(EnumName)='')]">
<xsl:sort select="LocalEnumName" data-type="text"/>
<xsl:text>
from enums.</xsl:text>
<xsl:value-of select="translate(LocalEnumName,'.','_')"/>
<xsl:text> import </xsl:text>
<xsl:call-template name="nt-case">
    <xsl:with-param name="type-name-text" select="LocalEnumName" />
</xsl:call-template>


</xsl:for-each>
<xsl:text>


__all__ = [
    "MarketTypeName",</xsl:text>
<xsl:for-each select="$airtable//ProtocolEnums/ProtocolEnum[(normalize-space(ProtocolName) ='scada')]">
<xsl:sort select="LocalEnumName" data-type="text"/>
<xsl:variable name="gt-enum-id" select="GtEnumId"/>



<xsl:text>
    "</xsl:text>
    <xsl:call-template name="nt-case">
        <xsl:with-param name="type-name-text" select="LocalEnumName" />
    </xsl:call-template>
    <xsl:text>",  # [</xsl:text>
    <xsl:value-of select="EnumName"/><xsl:text>.</xsl:text>
    <xsl:value-of select="EnumVersion"/>
    <xsl:text>](https://gridworks-type-registry.readthedocs.io/en/latest/enums.html#</xsl:text>
    <xsl:value-of select="translate(EnumName,'.','')"/>
    <xsl:text>)</xsl:text>
</xsl:for-each>

<xsl:text>
]</xsl:text>

<!-- Add newline at EOF for git and pre-commit-->
<xsl:text>&#10;</xsl:text>


                </xsl:element>
            </FileSetFile>


        </FileSet>
    </xsl:template>


</xsl:stylesheet>
