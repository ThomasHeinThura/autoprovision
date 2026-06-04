# Builds a WSO2 Identity Server 7.2.0 image with the MSSQL JDBC driver included.
# The stock wso2/wso2is image does NOT bundle a proprietary JDBC driver, so IS cannot talk to
# SQL Server without this. Mirrors images/apim-cp/Dockerfile. Default BASE_IMAGE is the public one.

ARG BASE_IMAGE=wso2/wso2is:7.2.0
FROM ${BASE_IMAGE}

ARG USER=wso2carbon
ARG USER_HOME=/home/${USER}
ARG WSO2_SERVER_NAME=wso2is
ARG WSO2_SERVER_VERSION=7.2.0
ARG WSO2_SERVER=${WSO2_SERVER_NAME}-${WSO2_SERVER_VERSION}
ARG WSO2_SERVER_HOME=${USER_HOME}/${WSO2_SERVER}

# Copy the MSSQL driver into components/lib (Carbon auto-converts the plain jar to an OSGi bundle).
ADD --chown=wso2carbon:wso2 https://repo1.maven.org/maven2/com/microsoft/sqlserver/mssql-jdbc/12.6.1.jre11/mssql-jdbc-12.6.1.jre11.jar ${WSO2_SERVER_HOME}/repository/components/lib/
