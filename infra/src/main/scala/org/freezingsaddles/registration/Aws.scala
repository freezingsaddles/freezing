package org.freezingsaddles.registration

import software.amazon.awssdk.core.sync.ResponseTransformer
import software.amazon.awssdk.http.urlconnection.UrlConnectionHttpClient
import software.amazon.awssdk.services.s3.S3Client
import software.amazon.awssdk.services.s3.model.GetObjectRequest
import software.amazon.awssdk.services.ssm.SsmClient
import software.amazon.awssdk.services.ssm.model.GetParameterRequest

/** The two AWS calls the handler makes, behind a trait so tests need neither. */
trait Aws:
  def readObject(bucket: String, key: String): Array[Byte]

  /** A SecureString parameter, decrypted. */
  def readParameter(name: String): String

object Aws:
  lazy val live: Aws = new Aws:
    private val http = UrlConnectionHttpClient.builder().build()
    private val s3   = S3Client.builder().httpClient(http).build()
    private val ssm  = SsmClient.builder().httpClient(http).build()

    def readObject(bucket: String, key: String): Array[Byte] =
      s3.getObject(
        GetObjectRequest.builder().bucket(bucket).key(key).build(),
        ResponseTransformer.toBytes(),
      ).asByteArray()

    def readParameter(name: String): String =
      ssm
        .getParameter(GetParameterRequest.builder().name(name).withDecryption(true).build())
        .parameter()
        .value()
end Aws
