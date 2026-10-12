-- Bảng kỹ thuật lưu phiên, ngoài hai bảng nghiệp vụ ROLE và USER.
USE [quan_ly_tro];
GO
SET XACT_ABORT ON;
GO
BEGIN TRY
    BEGIN TRANSACTION;
    IF OBJECT_ID(N'dbo.user', N'U') IS NULL
        THROW 50002, N'Chưa có bảng dbo.user.', 1;
    IF OBJECT_ID(N'dbo.auth_session', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.auth_session (
            token_hash CHAR(64) COLLATE Latin1_General_100_BIN2 NOT NULL CONSTRAINT PK_auth_session PRIMARY KEY,
            user_id BIGINT NOT NULL,
            expires_at DATETIME2(0) NOT NULL,
            created_at DATETIME2(0) NOT NULL CONSTRAINT DF_auth_session_created_at DEFAULT (SYSUTCDATETIME()),
            CONSTRAINT FK_auth_session_user FOREIGN KEY (user_id) REFERENCES dbo.[user](user_id)
        );
    END;
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'dbo.auth_session') AND name = N'IX_auth_session_user_id')
        CREATE INDEX IX_auth_session_user_id ON dbo.auth_session(user_id);
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'dbo.auth_session') AND name = N'IX_auth_session_expires_at')
        CREATE INDEX IX_auth_session_expires_at ON dbo.auth_session(expires_at);
    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO
