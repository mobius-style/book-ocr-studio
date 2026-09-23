"""Independent local exports; optional formats are generated on demand."""
from pathlib import Path
import streamlit as st
from delivery import ensure_delivery

def output_buttons(job, key):
    result=ensure_delivery(job)
    columns=st.columns(4)
    path=Path(result['path'])
    columns[0].download_button('MD for model input (with review suggestions)',path.read_bytes(),file_name=path.name,mime='text/markdown',key=key+'-md')
    formats=[('html','HTML with source images','text/html','Source images beside the text.'),
             ('pdf','PDF with source images and text','application/pdf','Source images followed by selectable OCR text and separate review suggestions.'),
             ('epub','EPUB for reading','application/epub+zip','Reflowable text, separate review suggestions and source images. Includes navigation.')]
    for column,(suffix,label,mime,help_text) in zip(columns[1:],formats):
        with column:
            if not result.get(suffix+'_path'):
                if st.button('Create '+suffix.upper(),key=key+'-make-'+suffix,help=help_text+' Generated locally without rerunning OCR or Gemma.'):
                    try:
                        with st.spinner('Creating '+suffix.upper()+' locally…'):
                            result=ensure_delivery(job,**{'include_'+suffix:True})
                    except Exception as exc:st.error('Export failed: '+str(exc))
            if result.get(suffix+'_path'):
                path=Path(result[suffix+'_path'])
                st.download_button(label,path.read_bytes(),file_name=path.name,mime=mime,key=key+'-'+suffix)
    st.caption('All exports are created on this computer. Reading text preserves the source language. Unapproved suggestions remain separate; PDF and EPUB are reading copies, not publisher-layout reproductions.')
    return result
