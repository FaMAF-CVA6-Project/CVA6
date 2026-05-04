#!/bin/bash

# Nombre de la carpeta de destino
DEST_DIR="cva6_files"

# Crear la carpeta de destino si no existe
mkdir -p "$DEST_DIR"

# Definir las rutas base
CVA6_REPO_DIR=$(pwd)
HPDCACHE_DIR="$CVA6_REPO_DIR/core/cache_subsystem/hpdcache"

echo "Iniciando la copia de archivos a $DEST_DIR..."
echo "CVA6_REPO_DIR = $CVA6_REPO_DIR"
echo "HPDCACHE_DIR = $HPDCACHE_DIR"
echo "------------------------------------------------"

# Función para procesar y copiar los archivos de una lista
procesar_lista() {
    local list_file=$1
    
    if [ ! -f "$list_file" ]; then
        echo "Error: No se encontró el archivo $list_file"
        return
    fi

    echo "Procesando $list_file..."

    while IFS= read -r line; do
        # Eliminar espacios en blanco al inicio y al final
        line=$(echo "$line" | xargs)
        
        # Ignorar líneas vacías, comentarios (//) y directivas de otros manifiestos (-F)
        if [[ -z "$line" || "$line" == //* || "$line" == -F* ]]; then
            continue
        fi

        # Reemplazar las variables por las rutas absolutas
        local path_str="${line//\$\{CVA6_REPO_DIR\}/$CVA6_REPO_DIR}"
        path_str="${path_str//\$\{HPDCACHE_DIR\}/$HPDCACHE_DIR}"

        # Lógica para directorios de inclusión (+incdir+)
        if [[ "$path_str" == +incdir+* ]]; then
            # Extraer solo la ruta quitando el prefijo '+incdir+'
            local inc_dir="${path_str#+incdir+}"
            
            if [ -d "$inc_dir" ]; then
                echo "  Copiando cabeceras desde: $inc_dir"
                # Usar find para buscar y copiar solo archivos relevantes sin recursión
                find "$inc_dir" -maxdepth 1 -type f \( -name "*.sv" -o -name "*.v" -o -name "*.svh" -o -name "*.vh" -o -name "*.h" \) -exec cp {} "$DEST_DIR/" \;
            else
                echo "  [Advertencia] Directorio +incdir+ no encontrado: $inc_dir"
            fi
            
        # Lógica para archivos individuales
        else
            if [ -f "$path_str" ]; then
                cp "$path_str" "$DEST_DIR/"
            else
                echo "  [Advertencia] Archivo no encontrado: $path_str"
            fi
        fi
    done < "$list_file"
}

# Procesar ambas listas
procesar_lista "Flist.cva6"
procesar_lista "hpdcache.Flist"

echo "------------------------------------------------"
echo "Proceso completado. Revisa la carpeta '$DEST_DIR'."
