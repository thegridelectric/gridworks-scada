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
    <xsl:include href="ScadaCommon.xslt"/>

    <xsl:template match="@*|node()">
        <xsl:copy>
            <xsl:apply-templates select="@*|node()" />
        </xsl:copy>
    </xsl:template>

    <xsl:template match="/">
        <FileSet>
            <FileSetFiles>
                <xsl:for-each select="$airtable//Schemas/Schema[(normalize-space(Alias) !='') and (MakeDataClass='true')  and (IsComponent='true') and (Status = 'Active')]">
                    <xsl:variable name="schema-alias" select="Alias" />  
                    <xsl:variable name="schema-id" select="SchemaId" />  
                    <xsl:variable name="class-name">
                        <xsl:call-template name="nt-case">
                            <xsl:with-param name="mp-schema-text" select="Alias" />
                        </xsl:call-template>
                    </xsl:variable>
                    <xsl:variable name="cac">
                        <xsl:for-each select="$airtable//SchemaAttributes/SchemaAttribute[(GtSchema = $schema-id) and (IsType = 'true')]">
                            <xsl:variable name="type-id" select="SubTypeFormat"/>
                            <xsl:for-each select="$airtable//Schemas/Schema[(SchemaId=$type-id)]">
                                <xsl:value-of select="DataClass"/>
                            </xsl:for-each>
                        </xsl:for-each>
                    </xsl:variable>
                    <FileSetFile>
                                <xsl:element name="RelativePath"><xsl:text>../../../../../gw_spaceheat/data_classes/components/</xsl:text>
                                <xsl:call-template name="python-case">
                                    <xsl:with-param name="camel-case-text" select="DataClass"  />
                                </xsl:call-template><xsl:text>_base.py</xsl:text></xsl:element>

                        <OverwriteMode>Always</OverwriteMode>
                        <xsl:element name="FileContents">

   
<xsl:text>"""</xsl:text><xsl:value-of select="DataClass"/><xsl:text>Base definition"""

from abc import abstractmethod
from typing import Optional, Dict

from schema.enums.make_model.make_model_map import MakeModel
from schema.gt.</xsl:text> <xsl:value-of select="translate(AliasRoot,'.','_')"/>
<xsl:text>.</xsl:text><xsl:value-of select="translate(Alias,'.','_')"/>
<xsl:text> import </xsl:text><xsl:value-of select="$class-name"/><xsl:text>
from data_classes.component import Component
from data_classes.errors import DcError
from data_classes.cacs.</xsl:text><xsl:call-template name="python-case">
    <xsl:with-param name="camel-case-text" select="translate($cac,'.','_')"  />
</xsl:call-template><xsl:text> import </xsl:text><xsl:value-of select="$cac"/>

<xsl:for-each select="$airtable//SchemaAttributes/SchemaAttribute[(GtSchema = $schema-id) and (IsEnum = 'true')]">

<xsl:text>
from schema.enums.</xsl:text>
<xsl:call-template name="python-case">
    <xsl:with-param name="camel-case-text" select="translate(EnumLocalName,'.','_')"  />
</xsl:call-template>
<xsl:text>.</xsl:text>
<xsl:call-template name="python-case">
    <xsl:with-param name="camel-case-text" select="translate(EnumLocalName,'.','_')"  />
</xsl:call-template>
<xsl:text>_map import </xsl:text>
<xsl:call-template name="nt-case">
    <xsl:with-param name="mp-schema-text" select="EnumLocalName" />
</xsl:call-template>
<xsl:text>Map</xsl:text>
</xsl:for-each>
<xsl:text>


class </xsl:text><xsl:value-of select="DataClass"/><xsl:text>Base(Component):
    _by_id: Dict = {}
    base_props = []</xsl:text>
    <xsl:for-each select="$airtable//SchemaAttributes/SchemaAttribute[(GtSchema = $schema-id) and ((IsPrimitive = 'true') or (IsEnum = 'true')) ]">
    <xsl:text>
    base_props.append("</xsl:text>
        <xsl:call-template name="python-case">
            <xsl:with-param name="camel-case-text" select="Value"  />
        </xsl:call-template><xsl:text>")</xsl:text>
    </xsl:for-each>
    <xsl:for-each select="$airtable//SchemaAttributes/SchemaAttribute[(GtSchema = $schema-id) and (IsType = 'true') ]">
    <xsl:text>
    base_props.append("</xsl:text>
        <xsl:call-template name="python-case">
            <xsl:with-param name="camel-case-text" select="Value"  />
        </xsl:call-template><xsl:text>_id")</xsl:text>
    </xsl:for-each>
    <xsl:text>

    def __init__(self, </xsl:text>
        <xsl:for-each select="$airtable//SchemaAttributes/SchemaAttribute[(GtSchema = $schema-id) and (IsPrimitive = 'true') and (IsRequired = 'true')]">
            <xsl:call-template name="python-case">
                <xsl:with-param name="camel-case-text" select="Value"  />
            </xsl:call-template><xsl:text>: </xsl:text>
            <xsl:call-template name="python-type">
                <xsl:with-param name="gw-type" select="PrimitiveType"/>
            </xsl:call-template>
        <xsl:text>,
                 </xsl:text>
        </xsl:for-each>
        <xsl:for-each select="$airtable//SchemaAttributes/SchemaAttribute[(GtSchema = $schema-id) and (IsEnum = 'true')]">
            <xsl:call-template name="python-case">
                <xsl:with-param name="camel-case-text" select="Value"  />
            </xsl:call-template><xsl:text>_gt_enum_symbol: str,
                 </xsl:text>
        </xsl:for-each>
        <xsl:for-each select="$airtable//SchemaAttributes/SchemaAttribute[(GtSchema = $schema-id) and (IsType = 'true')]">
        <xsl:call-template name="python-case">
                <xsl:with-param name="camel-case-text" select="Value"  />
            </xsl:call-template><xsl:text>_id: str,
                 </xsl:text>
        </xsl:for-each>
        <xsl:for-each select="$airtable//SchemaAttributes/SchemaAttribute[(GtSchema = $schema-id) and (IsPrimitive = 'true') and  not(IsRequired = 'true')]">
            <xsl:call-template name="python-case">
                <xsl:with-param name="camel-case-text" select="Value"  />
            </xsl:call-template><xsl:text>: Optional[</xsl:text>
            <xsl:call-template name="python-type">
                <xsl:with-param name="gw-type" select="PrimitiveType"/>
            </xsl:call-template>
            <xsl:text>] = None,
                 </xsl:text>
    </xsl:for-each>
        <xsl:text>):

        super(</xsl:text><xsl:value-of select="DataClass"/><xsl:text>Base, self).__init__(component_id=component_id,
                                             display_name=display_name,
                                             component_attribute_class_id=component_attribute_class_id,
                                             hw_uid=hw_uid)</xsl:text>
        <xsl:for-each select="$airtable//SchemaAttributes/SchemaAttribute[(GtSchema = $schema-id) and (IsPrimitive = 'true') and not (Value = 'ComponentId') and not (Value = 'DisplayName')]">
        <xsl:text>
        self.</xsl:text>
        <xsl:call-template name="python-case">
                <xsl:with-param name="camel-case-text" select="Value"  />
            </xsl:call-template><xsl:text> = </xsl:text>
            <xsl:call-template name="python-case">
                <xsl:with-param name="camel-case-text" select="Value"  />
            </xsl:call-template>
        </xsl:for-each>
        <xsl:for-each select="$airtable//SchemaAttributes/SchemaAttribute[(GtSchema = $schema-id) and (IsType = 'true')]">
        <xsl:text>
        self.</xsl:text>
        <xsl:call-template name="python-case">
                <xsl:with-param name="camel-case-text" select="Value"  />
            </xsl:call-template><xsl:text>_id = </xsl:text>
            <xsl:call-template name="python-case">
                <xsl:with-param name="camel-case-text" select="Value"  />
        </xsl:call-template><xsl:text>_id</xsl:text>

        </xsl:for-each>
        <xsl:for-each select="$airtable//SchemaAttributes/SchemaAttribute[(GtSchema = $schema-id) and (IsEnum = 'true')]">
        <xsl:text>
        self.</xsl:text>
        <xsl:call-template name="python-case">
                <xsl:with-param name="camel-case-text" select="Value"  />
            </xsl:call-template><xsl:text> = </xsl:text>
                <xsl:call-template name="nt-case">
                    <xsl:with-param name="mp-schema-text" select="EnumLocalName" />
                </xsl:call-template><xsl:text>Map.gt_to_local(</xsl:text>
                <xsl:value-of select="translate(EnumLocalName,'.','_')"/>
                <xsl:text>_gt_enum_symbol)</xsl:text>
        </xsl:for-each>                                    
    <xsl:text>   #
        </xsl:text><xsl:value-of select="DataClass"/><xsl:text>Base._by_id[self.component_id] = self
        Component.by_id[self.component_id] = self

    def update(self, type: </xsl:text><xsl:value-of select="$class-name"/><xsl:text>):
        self._check_immutability_constraints(type=type)

    def _check_immutability_constraints(self, type: </xsl:text><xsl:value-of select="$class-name"/><xsl:text>):</xsl:text>
        <xsl:for-each select="$airtable//SchemaAttributes/SchemaAttribute[(GtSchema = $schema-id) and (ImmutableInDc = 'true') and  ((IsEnum = 'true') or (IsPrimitive = 'true')) and (IsRequired = 'true')]">
        <xsl:text>
        if self.</xsl:text>  <xsl:call-template name="python-case">
            <xsl:with-param name="camel-case-text" select="Value"  />
        </xsl:call-template> <xsl:text> != type.</xsl:text>
        <xsl:value-of select="Value"/>
        <xsl:text>:
            raise DcError(f'</xsl:text> 
            <xsl:call-template name="python-case">
                <xsl:with-param name="camel-case-text" select="Value"  />
            </xsl:call-template>
            <xsl:text> must be immutable for {self}. '
                          f'Got {type.</xsl:text><xsl:value-of select="Value"/>  
                <xsl:text>}')</xsl:text>
        </xsl:for-each>
        <xsl:for-each select="$airtable//SchemaAttributes/SchemaAttribute[(GtSchema = $schema-id) and (ImmutableInDc = 'true') and not (IsRequired = 'true')]">
        <xsl:text>
        if self.</xsl:text>  <xsl:call-template name="python-case">
            <xsl:with-param name="camel-case-text" select="Value"  />
        </xsl:call-template> <xsl:text>:
            if self.</xsl:text>  <xsl:call-template name="python-case">
                <xsl:with-param name="camel-case-text" select="Value"  />
            </xsl:call-template> <xsl:text> != type.</xsl:text>
            <xsl:value-of select="Value"/>
            <xsl:text>:
                raise DcError(f'</xsl:text> 
                <xsl:call-template name="python-case">
                    <xsl:with-param name="camel-case-text" select="Value"  />
                </xsl:call-template>
                <xsl:text> must be immutable for {self}. '
                              f'Got {type.</xsl:text><xsl:value-of select="Value"/>  
                    <xsl:text>}')</xsl:text>
        </xsl:for-each>
        <xsl:for-each select="$airtable//SchemaAttributes/SchemaAttribute[(GtSchema = $schema-id) and (ImmutableInDc = 'true') and  (IsType = 'true')]">
        <xsl:text>
        if self.</xsl:text>  <xsl:call-template name="python-case">
            <xsl:with-param name="camel-case-text" select="Value"  />
        </xsl:call-template> <xsl:text>_id != type.</xsl:text>
        <xsl:value-of select="Value"/>
        <xsl:text>Id:
            raise DcError(f'</xsl:text> 
            <xsl:call-template name="python-case">
                <xsl:with-param name="camel-case-text" select="Value"  />
            </xsl:call-template>
            <xsl:text>_id must be immutable for {self}. '
                          f'Got {type.</xsl:text><xsl:value-of select="Value"/>  
                <xsl:text>Id}')</xsl:text>
        </xsl:for-each>

    <xsl:text>

    @property
    def cac(self) -> </xsl:text><xsl:value-of select="$cac"/>
    <xsl:text>:
        return </xsl:text><xsl:value-of select="$cac"/><xsl:text>.by_id[self.component_attribute_class_id]

    @property
    def make_model(self) -> MakeModel:
        return self.cac.make_model

    @abstractmethod
    def _check_update_axioms(self, type: </xsl:text><xsl:value-of select="$class-name"/><xsl:text>):
        raise NotImplementedError

    @abstractmethod
    def __repr__(self):
        raise NotImplementedError
</xsl:text>


                        </xsl:element>
                     </FileSetFile>
                </xsl:for-each>

            </FileSetFiles>
        </FileSet>
    </xsl:template>


</xsl:stylesheet>