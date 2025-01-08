from lxml import etree


def write_xliff(root, filename):
    with open(filename, "w+") as fp:
        # Fix identation of XML file
        etree.indent(root)
        """
        Hack to avoid conflicts with Pontoon, which uses single quotes
        for the XML declaration:
            1. Exclude the XML declaration when using etree.tostring()
            2. Manually add the declaration with double quotes
        """
        xliff_content = etree.tostring(
            root,
            encoding="UTF-8",
            xml_declaration=False,
            pretty_print=True,
        )
        xliff_content = (
            '<?xml version="1.0" encoding="UTF-8"?>\n' + xliff_content.decode("utf-8")
        )
        fp.write(xliff_content)
