# Tareas Viejas

- Revisar todos los parametros de gem5 con el comentario "# Revisar":
  - Hacer un microbenchmark con instrucciones comprimidas y verificar el parámetro decodeInputWidth y decodeCycleInput, comparar que pasa cuando deshabilitamos las instrucciones comprimidas.
  - Revisar la definicion de los parametros de las Caches y completar los de la Functional Units.
  - Verificar que es el LSQ y analizar esos parámetros. Probar con el benchmark de todos loads/store y compara la cantidad de accesos de memoria con la cantidad de ciclos respecto a verilator. Si la cantidad de acceso a memoria es correcta y la cantidad de ciclos tambien, nos quedamos tranquilo que estos parametros funcionan.
- Correr nuevamente el Daxpy y ver que las metricas tienen sentido respecto a la tablita. Si con el daxpy anda bien, hacer mas pruebas: multiplicación de matrices y predictor de salto. Probar algun programa de C.
- Redactar el analisis del gtkwave con el programa chiquito.
- Avanzar con el programa para sacar la metrica de D cache en Verilator.
- Correr un programa de multiplicacion de matrices de punto flotante
- Revisar en ambos visualizadores:
  - Probar programas con desfases en las instrucciones comprimidas y normales
  - El programa con todos los tipos de instrucciones
  - Revisar que den la misma cantidad de ciclos, miss de cache, miss de i cache, etc si es posible
  - Daxpy Normal
  - Programa con dependencia de datos
  - Loop basico con instrucciones enteras/flotantes
  - Programa que haga saltar miss de i cache
  - Programa que haga saltar miss de d cache
  - Probar varias configuraciones del gem5 para ver si realmente se esta cambiando algo
  - Programas que provoquen saltos

# Tareas Nuevas

- Configurar gem5 en la versión más simple posible (para ejecutar de a 1 instrucción) y analizar cómo se ve. Si es más simple que la ejecución actual, empezar las pruebas con este micro. Sino, usar la configuración actual (ajustada a CVA6)
- Probar un código que sólo tenga instrucciones artimeticas (acá también se pueden ver comprimidas vs. no comprimidas)
- Probar código con accesos a memoria (comenzar con daxpy) y analizar cómo cambia la ejecución para distintas configuraciones de caché