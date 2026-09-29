# Passerelle JDK Talend

Application Streamlit d’aide à la préparation d’une migration de jobs Talend de Java 11 vers Java 17, dans le contexte d’une montée de Talend 2023-06 vers Talend 2026-06.

## Démarrage

```powershell
<python> -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

Remplacez `<python>` par l’interpréteur Python disponible sur votre poste. Python 3.10 ou plus récent est recommandé.

## Utilisation

1. Exportez le projet ou les jobs concernés depuis Talend Studio sous forme d’archive ZIP.
2. Chargez l’archive dans l’application et lancez l’analyse.
3. Consultez les règles détectées et téléchargez le rapport CSV.
4. Cochez explicitement l’option de mise à jour pour produire une copie ZIP. Seules les cibles Java 11 reconnues dans les réglages Maven, Gradle et propriétés sont modifiées en Java 17.
5. Réimportez et validez les jobs avec les outils supportés par votre version de Talend avant toute mise en production.

## Périmètre et limites

L’analyse est statique et locale à l’instance Streamlit. Elle repère les références à JAXB, Java Activation, certaines API internes du JDK, Nashorn, des accès réflexifs et les cibles Java explicites inférieures à 17. Elle ne compile pas les jobs et ne connaît pas le graphe des dépendances du runtime Talend.

Cette application ne remplace pas une migration officielle de Talend 2023-06 vers 2026-06 : elle ne transforme pas les métadonnées propriétaires `.item`, les composants, les routines ni les contextes Talend. Les résultats doivent être revus et validés dans Talend Studio avec les runtimes et pilotes réellement utilisés.

Les fichiers individuels de plus de 5 Mio et les fichiers au-delà de 2 000 entrées analysables sont ignorés pour maîtriser les ressources. Les archives ne sont pas extraites sur le disque.

## Tests

```powershell
python -m unittest discover -s tests -v
```